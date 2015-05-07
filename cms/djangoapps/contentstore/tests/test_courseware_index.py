"""
Testing indexing of the courseware as it is changed
"""
import ddt
from lazy.lazy import lazy
import time
from datetime import datetime
from mock import patch
from pytz import UTC
from uuid import uuid4
from unittest import skip

from course_modes.models import CourseMode
from xmodule.library_tools import normalize_key_for_search
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.django import SignalHandler
from xmodule.modulestore.edit_info import EditInfoMixin
from xmodule.modulestore.exceptions import ItemNotFoundError
from xmodule.modulestore.inheritance import InheritanceMixin
from xmodule.modulestore.mixed import MixedModuleStore
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory, LibraryFactory
from xmodule.modulestore.tests.mongo_connection import MONGO_PORT_NUM, MONGO_HOST
from xmodule.modulestore.tests.test_cross_modulestore_import_export import MongoContentstoreBuilder
from xmodule.modulestore.tests.utils import create_modulestore_instance, LocationMixin, MixedSplitTestCase
from xmodule.tests import DATA_DIR
from xmodule.x_module import XModuleMixin

from search.search_engine_base import SearchEngine

from contentstore.courseware_index import (
    CoursewareSearchIndexer,
    LibrarySearchIndexer,
    SearchIndexingError,
    CourseAboutSearchIndexer,
)
from contentstore.signals import listen_for_course_publish, listen_for_library_update


COURSE_CHILD_STRUCTURE = {
    "course": "chapter",
    "chapter": "sequential",
    "sequential": "vertical",
    "vertical": "html",
}


def create_children(store, parent, category, load_factor):
    """ create load_factor children within the given parent; recursively call to insert children when appropriate """
    created_count = 0
    for child_index in range(0, load_factor):
        child_object = ItemFactory.create(
            parent_location=parent.location,
            category=category,
            display_name=u"{} {} {}".format(category, child_index, time.clock()),
            modulestore=store,
            publish_item=True,
            start=datetime(2015, 3, 1, tzinfo=UTC),
        )
        created_count += 1

        if category in COURSE_CHILD_STRUCTURE:
            created_count += create_children(store, child_object, COURSE_CHILD_STRUCTURE[category], load_factor)

    return created_count


def create_large_course(store, load_factor):
    """
    Create a large course, note that the number of blocks created will be
    load_factor ^ 4 - e.g. load_factor of 10 => 10 chapters, 100
    sequentials, 1000 verticals, 10000 html blocks
    """
    course = CourseFactory.create(modulestore=store, start=datetime(2015, 3, 1, tzinfo=UTC))
    with store.bulk_operations(course.id):
        child_count = create_children(store, course, COURSE_CHILD_STRUCTURE["course"], load_factor)
    return course, child_count


class MixedWithOptionsTestCase(MixedSplitTestCase):
    """ Base class for test cases within this file """
    HOST = MONGO_HOST
    PORT = MONGO_PORT_NUM
    DATABASE = 'test_mongo_%s' % uuid4().hex[:5]
    COLLECTION = 'modulestore'
    ASSET_COLLECTION = 'assetstore'
    DEFAULT_CLASS = 'xmodule.raw_module.RawDescriptor'
    RENDER_TEMPLATE = lambda t_n, d, ctx=None, nsp='main': ''
    modulestore_options = {
        'default_class': DEFAULT_CLASS,
        'fs_root': DATA_DIR,
        'render_template': RENDER_TEMPLATE,
        'xblock_mixins': (EditInfoMixin, InheritanceMixin, LocationMixin, XModuleMixin),
    }
    DOC_STORE_CONFIG = {
        'host': HOST,
        'port': PORT,
        'db': DATABASE,
        'collection': COLLECTION,
        'asset_collection': ASSET_COLLECTION,
    }
    OPTIONS = {
        'stores': [
            {
                'NAME': 'draft',
                'ENGINE': 'xmodule.modulestore.mongo.draft.DraftModuleStore',
                'DOC_STORE_CONFIG': DOC_STORE_CONFIG,
                'OPTIONS': modulestore_options
            },
            {
                'NAME': 'split',
                'ENGINE': 'xmodule.modulestore.split_mongo.split_draft.DraftVersioningModuleStore',
                'DOC_STORE_CONFIG': DOC_STORE_CONFIG,
                'OPTIONS': modulestore_options
            },
            {
                'NAME': 'xml',
                'ENGINE': 'xmodule.modulestore.xml.XMLModuleStore',
                'OPTIONS': {
                    'data_dir': DATA_DIR,
                    'default_class': 'xmodule.hidden_module.HiddenDescriptor',
                    'xblock_mixins': modulestore_options['xblock_mixins'],
                }
            },
        ],
        'xblock_mixins': modulestore_options['xblock_mixins'],
    }

    INDEX_NAME = None
    DOCUMENT_TYPE = None

    def setUp(self):
        super(MixedWithOptionsTestCase, self).setUp()

    def setup_course_base(self, store):
        """ base version of setup_course_base is a no-op """
        pass

    @lazy
    def searcher(self):
        """ Centralized call to getting the search engine for the test """
        return SearchEngine.get_search_engine(self.INDEX_NAME)

    def _get_default_search(self):
        """ Returns field_dictionary for default search """
        return {}

    def search(self, field_dictionary=None, query_string=None):
        """ Performs index search according to passed parameters """
        fields = field_dictionary if field_dictionary else self._get_default_search()
        return self.searcher.search(query_string=query_string, field_dictionary=fields, doc_type=self.DOCUMENT_TYPE)

    def _perform_test_using_store(self, store_type, test_to_perform):
        """ Helper method to run a test function that uses a specific store """
        with MongoContentstoreBuilder().build() as contentstore:
            store = MixedModuleStore(
                contentstore=contentstore,
                create_modulestore_instance=create_modulestore_instance,
                mappings={},
                **self.OPTIONS
            )
            self.addCleanup(store.close_all_connections)

            with store.default_store(store_type):
                self.setup_course_base(store)
                test_to_perform(store)

    def publish_item(self, store, item_location):
        """ publish the item at the given location """
        with store.branch_setting(ModuleStoreEnum.Branch.draft_preferred):
            store.publish(item_location, ModuleStoreEnum.UserID.test)

    def delete_item(self, store, item_location):
        """ delete the item at the given location """
        with store.branch_setting(ModuleStoreEnum.Branch.draft_preferred):
            store.delete_item(item_location, ModuleStoreEnum.UserID.test)

    def update_item(self, store, item):
        """ update the item at the given location """
        with store.branch_setting(ModuleStoreEnum.Branch.draft_preferred):
            store.update_item(item, ModuleStoreEnum.UserID.test)

    def update_about_item(self, store, about_key, data):
        """
        Update the about item with the new data blob. If data is None, then
        delete the about item.
        """
        temploc = self.course.id.make_usage_key('about', about_key)
        if data is None:
            try:
                self.delete_item(store, temploc)
            # Ignore an attempt to delete an item that doesn't exist
            except ValueError:
                pass
        else:
            try:
                about_item = store.get_item(temploc)
            except ItemNotFoundError:
                about_item = store.create_xblock(self.course.runtime, self.course.id, 'about', about_key)
            about_item.data = data
            store.update_item(about_item, ModuleStoreEnum.UserID.test, allow_not_found=True)


@ddt.ddt
class TestCoursewareSearchIndexer(MixedWithOptionsTestCase):
    """ Tests the operation of the CoursewareSearchIndexer """

    WORKS_WITH_STORES = (ModuleStoreEnum.Type.mongo, ModuleStoreEnum.Type.split)

    def setUp(self):
        super(TestCoursewareSearchIndexer, self).setUp()

        self.course = None
        self.chapter = None
        self.sequential = None
        self.vertical = None
        self.html_unit = None

    def setup_course_base(self, store):
        """
        Set up the for the course outline tests.
        """
        self.course = CourseFactory.create(
            modulestore=store,
            start=datetime(2015, 3, 1, tzinfo=UTC),
            display_name="Search Index Test Course"
        )

        self.chapter = ItemFactory.create(
            parent_location=self.course.location,
            category='chapter',
            display_name="Week 1",
            modulestore=store,
            publish_item=True,
            start=datetime(2015, 3, 1, tzinfo=UTC),
        )
        self.sequential = ItemFactory.create(
            parent_location=self.chapter.location,
            category='sequential',
            display_name="Lesson 1",
            modulestore=store,
            publish_item=True,
            start=datetime(2015, 3, 1, tzinfo=UTC),
        )
        self.vertical = ItemFactory.create(
            parent_location=self.sequential.location,
            category='vertical',
            display_name='Subsection 1',
            modulestore=store,
            publish_item=True,
            start=datetime(2015, 4, 1, tzinfo=UTC),
        )
        # unspecified start - should inherit from container
        self.html_unit = ItemFactory.create(
            parent_location=self.vertical.location,
            category="html",
            display_name="Html Content",
            modulestore=store,
            publish_item=False,
        )

    INDEX_NAME = CoursewareSearchIndexer.INDEX_NAME
    DOCUMENT_TYPE = CoursewareSearchIndexer.DOCUMENT_TYPE

    def reindex_course(self, store):
        """ kick off complete reindex of the course """
        return CoursewareSearchIndexer.do_course_reindex(store, self.course.id)

    def index_recent_changes(self, store, since_time):
        """ index course using recent changes """
        trigger_time = datetime.now(UTC)
        return CoursewareSearchIndexer.index(
            store,
            self.course.id,
            triggered_at=trigger_time,
            reindex_age=(trigger_time - since_time)
        )

    def _get_default_search(self):
        return {"course": unicode(self.course.id)}

    def _test_indexing_course(self, store):
        """ indexing course tests """
        response = self.search()
        self.assertEqual(response["total"], 0)

        # Only published modules should be in the index
        added_to_index = self.reindex_course(store)
        self.assertEqual(added_to_index, 3)
        response = self.search()
        self.assertEqual(response["total"], 3)

        # Publish the vertical as is, and any unpublished children should now be available
        self.publish_item(store, self.vertical.location)
        self.reindex_course(store)
        response = self.search()
        self.assertEqual(response["total"], 4)

    def _test_not_indexing_unpublished_content(self, store):
        """ add a new one, only appers in index once added """
        # Publish the vertical to start with
        self.publish_item(store, self.vertical.location)
        self.reindex_course(store)
        response = self.search()
        self.assertEqual(response["total"], 4)

        # Now add a new unit to the existing vertical
        ItemFactory.create(
            parent_location=self.vertical.location,
            category="html",
            display_name="Some other content",
            publish_item=False,
            modulestore=store,
        )
        self.reindex_course(store)
        response = self.search()
        self.assertEqual(response["total"], 4)

        # Now publish it and we should find it
        # Publish the vertical as is, and everything should be available
        self.publish_item(store, self.vertical.location)
        self.reindex_course(store)
        response = self.search()
        self.assertEqual(response["total"], 5)

    def _test_deleting_item(self, store):
        """ test deleting an item """
        # Publish the vertical to start with
        self.publish_item(store, self.vertical.location)
        self.reindex_course(store)
        response = self.search()
        self.assertEqual(response["total"], 4)

        # just a delete should not change anything
        self.delete_item(store, self.html_unit.location)
        self.reindex_course(store)
        response = self.search()
        self.assertEqual(response["total"], 4)

        # but after publishing, we should no longer find the html_unit
        self.publish_item(store, self.vertical.location)
        self.reindex_course(store)
        response = self.search()
        self.assertEqual(response["total"], 3)

    def _test_not_indexable(self, store):
        """ test not indexable items """
        # Publish the vertical to start with
        self.publish_item(store, self.vertical.location)
        self.reindex_course(store)
        response = self.search()
        self.assertEqual(response["total"], 4)

        # Add a non-indexable item
        ItemFactory.create(
            parent_location=self.vertical.location,
            category="openassessment",
            display_name="Some other content",
            publish_item=False,
            modulestore=store,
        )
        self.reindex_course(store)
        response = self.search()
        self.assertEqual(response["total"], 4)

        # even after publishing, we should not find the non-indexable item
        self.publish_item(store, self.vertical.location)
        self.reindex_course(store)
        response = self.search()
        self.assertEqual(response["total"], 4)

    def _test_start_date_propagation(self, store):
        """ make sure that the start date is applied at the right level """
        early_date = self.course.start
        later_date = self.vertical.start

        # Publish the vertical
        self.publish_item(store, self.vertical.location)
        self.reindex_course(store)
        response = self.search()
        self.assertEqual(response["total"], 4)

        results = response["results"]
        date_map = {
            unicode(self.chapter.location): early_date,
            unicode(self.sequential.location): early_date,
            unicode(self.vertical.location): later_date,
            unicode(self.html_unit.location): later_date,
        }
        for result in results:
            self.assertEqual(result["data"]["start_date"], date_map[result["data"]["id"]])

    @patch('django.conf.settings.SEARCH_ENGINE', None)
    def _test_search_disabled(self, store):
        """ if search setting has it as off, confirm that nothing is indexed """
        indexed_count = self.reindex_course(store)
        self.assertFalse(indexed_count)

    def _test_time_based_index(self, store):
        """ Make sure that a time based request to index does not index anything too old """
        self.publish_item(store, self.vertical.location)
        indexed_count = self.reindex_course(store)
        self.assertEqual(indexed_count, 4)

        # Add a new sequential
        sequential2 = ItemFactory.create(
            parent_location=self.chapter.location,
            category='sequential',
            display_name='Section 2',
            modulestore=store,
            publish_item=True,
            start=datetime(2015, 3, 1, tzinfo=UTC),
        )

        # add a new vertical
        vertical2 = ItemFactory.create(
            parent_location=sequential2.location,
            category='vertical',
            display_name='Subsection 2',
            modulestore=store,
            publish_item=True,
        )
        ItemFactory.create(
            parent_location=vertical2.location,
            category="html",
            display_name="Some other content",
            publish_item=False,
            modulestore=store,
        )

        before_time = datetime.now(UTC)
        self.publish_item(store, vertical2.location)
        # index based on time, will include an index of the origin sequential
        # because it is in a common subtree but not of the original vertical
        # because the original sequential's subtree is too old
        new_indexed_count = self.index_recent_changes(store, before_time)
        self.assertEqual(new_indexed_count, 5)

        # full index again
        indexed_count = self.reindex_course(store)
        self.assertEqual(indexed_count, 7)

    def _test_course_about_property_index(self, store):
        """ Test that informational properties in the course object end up in the course_info index """
        display_name = "Help, I need somebody!"
        self.course.display_name = display_name
        self.update_item(store, self.course)
        self.reindex_course(store)
        response = self.searcher.search(
            doc_type=CourseAboutSearchIndexer.DISCOVERY_DOCUMENT_TYPE,
            field_dictionary={"course": unicode(self.course.id)}
        )
        self.assertEqual(response["total"], 1)
        self.assertEqual(response["results"][0]["data"]["content"]["display_name"], display_name)

    def _test_course_about_store_index(self, store):
        """ Test that informational properties in the about store end up in the course_info index """
        short_description = "Not just anybody"
        self.update_about_item(store, "short_description", short_description)
        self.reindex_course(store)
        response = self.searcher.search(
            doc_type=CourseAboutSearchIndexer.DISCOVERY_DOCUMENT_TYPE,
            field_dictionary={"course": unicode(self.course.id)}
        )
        self.assertEqual(response["total"], 1)
        self.assertEqual(response["results"][0]["data"]["content"]["short_description"], short_description)

    def _test_course_about_mode_index(self, store):
        """ Test that informational properties in the course modes store end up in the course_info index """
        honour_mode = CourseMode(
            course_id=unicode(self.course.id),
            mode_slug=CourseMode.HONOR,
            mode_display_name=CourseMode.HONOR
        )
        honour_mode.save()
        verified_mode = CourseMode(
            course_id=unicode(self.course.id),
            mode_slug=CourseMode.VERIFIED,
            mode_display_name=CourseMode.VERIFIED
        )
        verified_mode.save()
        self.reindex_course(store)

        response = self.searcher.search(
            doc_type=CourseAboutSearchIndexer.DISCOVERY_DOCUMENT_TYPE,
            field_dictionary={"course": unicode(self.course.id)}
        )
        self.assertEqual(response["total"], 1)
        self.assertIn(CourseMode.HONOR, response["results"][0]["data"]["modes"])
        self.assertIn(CourseMode.VERIFIED, response["results"][0]["data"]["modes"])

    def _test_course_location_info(self, store):
        """ Test that course location information is added to index """
        self.publish_item(store, self.vertical.location)
        self.reindex_course(store)
        response = self.search(query_string="Html Content")
        self.assertEqual(response["total"], 1)

        result = response["results"][0]["data"]
        self.assertEqual(result["course_name"], "Search Index Test Course")
        self.assertEqual(result["location"], ["Week 1", "Lesson 1", "Subsection 1"])

    def _test_course_location_null(self, store):
        """ Test that course location information is added to index """
        sequential2 = ItemFactory.create(
            parent_location=self.chapter.location,
            category='sequential',
            display_name=None,
            modulestore=store,
            publish_item=True,
            start=datetime(2015, 3, 1, tzinfo=UTC),
        )
        # add a new vertical
        vertical2 = ItemFactory.create(
            parent_location=sequential2.location,
            category='vertical',
            display_name='Subsection 2',
            modulestore=store,
            publish_item=True,
        )
        ItemFactory.create(
            parent_location=vertical2.location,
            category="html",
            display_name="Find Me",
            publish_item=True,
            modulestore=store,
        )
        self.reindex_course(store)
        response = self.search(query_string="Find Me")
        self.assertEqual(response["total"], 1)

        result = response["results"][0]["data"]
        self.assertEqual(result["course_name"], "Search Index Test Course")
        self.assertEqual(result["location"], ["Week 1", CoursewareSearchIndexer.UNNAMED_MODULE_NAME, "Subsection 2"])

    @patch('django.conf.settings.SEARCH_ENGINE', 'search.tests.utils.ErroringIndexEngine')
    def _test_exception(self, store):
        """ Test that exception within indexing yields a SearchIndexingError """
        self.publish_item(store, self.vertical.location)
        with self.assertRaises(SearchIndexingError):
            self.reindex_course(store)

    @ddt.data(*WORKS_WITH_STORES)
    def test_indexing_course(self, store_type):
        self._perform_test_using_store(store_type, self._test_indexing_course)

    @ddt.data(*WORKS_WITH_STORES)
    def test_not_indexing_unpublished_content(self, store_type):
        self._perform_test_using_store(store_type, self._test_not_indexing_unpublished_content)

    @ddt.data(*WORKS_WITH_STORES)
    def test_deleting_item(self, store_type):
        self._perform_test_using_store(store_type, self._test_deleting_item)

    @ddt.data(*WORKS_WITH_STORES)
    def test_not_indexable(self, store_type):
        self._perform_test_using_store(store_type, self._test_not_indexable)

    @ddt.data(*WORKS_WITH_STORES)
    def test_start_date_propagation(self, store_type):
        self._perform_test_using_store(store_type, self._test_start_date_propagation)

    @ddt.data(*WORKS_WITH_STORES)
    def test_search_disabled(self, store_type):
        self._perform_test_using_store(store_type, self._test_search_disabled)

    @ddt.data(*WORKS_WITH_STORES)
    def test_time_based_index(self, store_type):
        self._perform_test_using_store(store_type, self._test_time_based_index)

    @ddt.data(*WORKS_WITH_STORES)
    def test_exception(self, store_type):
        self._perform_test_using_store(store_type, self._test_exception)

    @ddt.data(*WORKS_WITH_STORES)
    def test_course_about_property_index(self, store_type):
        self._perform_test_using_store(store_type, self._test_course_about_property_index)

    @ddt.data(*WORKS_WITH_STORES)
    def test_course_about_store_index(self, store_type):
        self._perform_test_using_store(store_type, self._test_course_about_store_index)

    @ddt.data(*WORKS_WITH_STORES)
    def test_course_about_mode_index(self, store_type):
        self._perform_test_using_store(store_type, self._test_course_about_mode_index)

    @ddt.data(*WORKS_WITH_STORES)
    def test_course_location_info(self, store_type):
        self._perform_test_using_store(store_type, self._test_course_location_info)

    @ddt.data(*WORKS_WITH_STORES)
    def test_course_location_null(self, store_type):
        self._perform_test_using_store(store_type, self._test_course_location_null)


@patch('django.conf.settings.SEARCH_ENGINE', 'search.tests.utils.ForceRefreshElasticSearchEngine')
@ddt.ddt
class TestLargeCourseDeletions(MixedWithOptionsTestCase):
    """ Tests to excerise deleting items from a course """

    WORKS_WITH_STORES = (ModuleStoreEnum.Type.mongo, ModuleStoreEnum.Type.split)

    def _clean_course_id(self):
        """ Clean all documents from the index that have a specific course provided """
        if self.course_id:

            response = self.searcher.search(field_dictionary={"course": self.course_id})
            while response["total"] > 0:
                for item in response["results"]:
                    self.searcher.remove(CoursewareSearchIndexer.DOCUMENT_TYPE, item["data"]["id"])
                response = self.searcher.search(field_dictionary={"course": self.course_id})
        self.course_id = None

    def setUp(self):
        super(TestLargeCourseDeletions, self).setUp()
        self.course_id = None

    def tearDown(self):
        super(TestLargeCourseDeletions, self).tearDown()
        self._clean_course_id()

    def assert_search_count(self, expected_count):
        """ Check that the search within this course will yield the expected number of results """

        response = self.searcher.search(field_dictionary={"course": self.course_id})
        self.assertEqual(response["total"], expected_count)

    def _do_test_large_course_deletion(self, store, load_factor):
        """ Test that deleting items from a course works even when present within a very large course """
        def id_list(top_parent_object):
            """ private function to get ids from object down the tree """
            list_of_ids = [unicode(top_parent_object.location)]
            for child in top_parent_object.get_children():
                list_of_ids.extend(id_list(child))
            return list_of_ids

        course, course_size = create_large_course(store, load_factor)
        self.course_id = unicode(course.id)

        # index full course
        CoursewareSearchIndexer.do_course_reindex(store, course.id)

        self.assert_search_count(course_size)

        # reload course to allow us to delete one single unit
        course = store.get_course(course.id, depth=1)

        # delete the first chapter
        chapter_to_delete = course.get_children()[0]
        self.delete_item(store, chapter_to_delete.location)

        # index and check correctness
        CoursewareSearchIndexer.do_course_reindex(store, course.id)
        deleted_count = 1 + load_factor + (load_factor ** 2) + (load_factor ** 3)
        self.assert_search_count(course_size - deleted_count)

    def _test_large_course_deletion(self, store):
        """ exception catch-ing wrapper around large test course test with deletions """
        # load_factor of 6 (1296 items) takes about 5 minutes to run on devstack on a laptop
        # load_factor of 7 (2401 items) takes about 70 minutes to run on devstack on a laptop
        # load_factor of 8 (4096 items) takes just under 3 hours to run on devstack on a laptop
        load_factor = 6
        try:
            self._do_test_large_course_deletion(store, load_factor)
        except:  # pylint: disable=bare-except
            # Catch any exception here to see when we fail
            print "Failed with load_factor of {}".format(load_factor)

    @skip(("This test is to see how we handle very large courses, to ensure that the delete"
           "procedure works smoothly - too long to run during the normal course of things"))
    @ddt.data(*WORKS_WITH_STORES)
    def test_large_course_deletion(self, store_type):
        self._perform_test_using_store(store_type, self._test_large_course_deletion)


class TestTaskExecution(ModuleStoreTestCase):
    """
    Set of tests to ensure that the task code will do the right thing when
    executed directly. The test course and library gets created without the listeners
    being present, which allows us to ensure that when the listener is
    executed, it is done as expected.
    """

    def setUp(self):
        super(TestTaskExecution, self).setUp()
        SignalHandler.course_published.disconnect(listen_for_course_publish)
        SignalHandler.library_updated.disconnect(listen_for_library_update)
        self.course = CourseFactory.create(start=datetime(2015, 3, 1, tzinfo=UTC))

        self.chapter = ItemFactory.create(
            parent_location=self.course.location,
            category='chapter',
            display_name="Week 1",
            publish_item=True,
            start=datetime(2015, 3, 1, tzinfo=UTC),
        )
        self.sequential = ItemFactory.create(
            parent_location=self.chapter.location,
            category='sequential',
            display_name="Lesson 1",
            publish_item=True,
            start=datetime(2015, 3, 1, tzinfo=UTC),
        )
        self.vertical = ItemFactory.create(
            parent_location=self.sequential.location,
            category='vertical',
            display_name='Subsection 1',
            publish_item=True,
            start=datetime(2015, 4, 1, tzinfo=UTC),
        )
        # unspecified start - should inherit from container
        self.html_unit = ItemFactory.create(
            parent_location=self.vertical.location,
            category="html",
            display_name="Html Content",
            publish_item=False,
        )

        self.library = LibraryFactory.create()

        self.library_block1 = ItemFactory.create(
            parent_location=self.library.location,
            category="html",
            display_name="Html Content",
            publish_item=False,
        )

        self.library_block2 = ItemFactory.create(
            parent_location=self.library.location,
            category="html",
            display_name="Html Content 2",
            publish_item=False,
        )

    def test_task_indexing_course(self):
        """ Making sure that the receiver correctly fires off the task when invoked by signal """
        searcher = SearchEngine.get_search_engine(CoursewareSearchIndexer.INDEX_NAME)
        response = searcher.search(
            doc_type=CoursewareSearchIndexer.DOCUMENT_TYPE,
            field_dictionary={"course": unicode(self.course.id)}
        )
        self.assertEqual(response["total"], 0)

        listen_for_course_publish(self, self.course.id)

        # Note that this test will only succeed if celery is working in inline mode
        response = searcher.search(
            doc_type=CoursewareSearchIndexer.DOCUMENT_TYPE,
            field_dictionary={"course": unicode(self.course.id)}
        )
        self.assertEqual(response["total"], 3)

    def test_task_library_update(self):
        """ Making sure that the receiver correctly fires off the task when invoked by signal """
        searcher = SearchEngine.get_search_engine(LibrarySearchIndexer.INDEX_NAME)
        library_search_key = unicode(normalize_key_for_search(self.library.location.library_key))
        response = searcher.search(field_dictionary={"library": library_search_key})
        self.assertEqual(response["total"], 0)

        listen_for_library_update(self, self.library.location.library_key)

        # Note that this test will only succeed if celery is working in inline mode
        response = searcher.search(field_dictionary={"library": library_search_key})
        self.assertEqual(response["total"], 2)


@ddt.ddt
class TestLibrarySearchIndexer(MixedWithOptionsTestCase):
    """ Tests the operation of the CoursewareSearchIndexer """

    # libraries work only with split, so do library indexer
    WORKS_WITH_STORES = (ModuleStoreEnum.Type.split, )

    def setUp(self):
        super(TestLibrarySearchIndexer, self).setUp()

        self.library = None
        self.html_unit1 = None
        self.html_unit2 = None

    def setup_course_base(self, store):
        """
        Set up the for the course outline tests.
        """
        self.library = LibraryFactory.create(modulestore=store)

        self.html_unit1 = ItemFactory.create(
            parent_location=self.library.location,
            category="html",
            display_name="Html Content",
            modulestore=store,
            publish_item=False,
        )

        self.html_unit2 = ItemFactory.create(
            parent_location=self.library.location,
            category="html",
            display_name="Html Content 2",
            modulestore=store,
            publish_item=False,
        )

    INDEX_NAME = LibrarySearchIndexer.INDEX_NAME
    DOCUMENT_TYPE = LibrarySearchIndexer.DOCUMENT_TYPE

    def _get_default_search(self):
        """ Returns field_dictionary for default search """
        return {"library": unicode(self.library.location.library_key.replace(version_guid=None, branch=None))}

    def reindex_library(self, store):
        """ kick off complete reindex of the course """
        return LibrarySearchIndexer.do_library_reindex(store, self.library.location.library_key)

    def _get_contents(self, response):
        """ Extracts contents from search response """
        return [item['data']['content'] for item in response['results']]

    def _test_indexing_library(self, store):
        """ indexing course tests """
        self.reindex_library(store)
        response = self.search()
        self.assertEqual(response["total"], 2)

        added_to_index = self.reindex_library(store)
        self.assertEqual(added_to_index, 2)
        response = self.search()
        self.assertEqual(response["total"], 2)

    def _test_creating_item(self, store):
        """ test updating an item """
        self.reindex_library(store)
        response = self.search()
        self.assertEqual(response["total"], 2)

        # updating a library item causes immediate reindexing
        data = "Some data"
        ItemFactory.create(
            parent_location=self.library.location,
            category="html",
            display_name="Html Content 3",
            data=data,
            modulestore=store,
            publish_item=False,
        )

        self.reindex_library(store)
        response = self.search()
        self.assertEqual(response["total"], 3)
        html_contents = [cont['html_content'] for cont in self._get_contents(response)]
        self.assertIn(data, html_contents)

    def _test_updating_item(self, store):
        """ test updating an item """
        self.reindex_library(store)
        response = self.search()
        self.assertEqual(response["total"], 2)

        # updating a library item causes immediate reindexing
        new_data = "I'm new data"
        self.html_unit1.data = new_data
        self.update_item(store, self.html_unit1)
        self.reindex_library(store)
        response = self.search()
        # TODO: MockSearchEngine never updates existing item: returns 3 items here - uncomment when it's fixed
        # self.assertEqual(response["total"], 2)
        html_contents = [cont['html_content'] for cont in self._get_contents(response)]
        self.assertIn(new_data, html_contents)

    def _test_deleting_item(self, store):
        """ test deleting an item """
        self.reindex_library(store)
        response = self.search()
        self.assertEqual(response["total"], 2)

        # deleting a library item causes immediate reindexing
        self.delete_item(store, self.html_unit1.location)
        self.reindex_library(store)
        response = self.search()
        self.assertEqual(response["total"], 1)

    def _test_not_indexable(self, store):
        """ test not indexable items """
        self.reindex_library(store)
        response = self.search()
        self.assertEqual(response["total"], 2)

        # Add a non-indexable item
        ItemFactory.create(
            parent_location=self.library.location,
            category="openassessment",
            display_name="Assessment",
            publish_item=False,
            modulestore=store,
        )
        self.reindex_library(store)
        response = self.search()
        self.assertEqual(response["total"], 2)

    @patch('django.conf.settings.SEARCH_ENGINE', None)
    def _test_search_disabled(self, store):
        """ if search setting has it as off, confirm that nothing is indexed """
        indexed_count = self.reindex_library(store)
        self.assertFalse(indexed_count)

    @patch('django.conf.settings.SEARCH_ENGINE', 'search.tests.utils.ErroringIndexEngine')
    def _test_exception(self, store):
        """ Test that exception within indexing yields a SearchIndexingError """
        with self.assertRaises(SearchIndexingError):
            self.reindex_library(store)

    @ddt.data(*WORKS_WITH_STORES)
    def test_indexing_library(self, store_type):
        self._perform_test_using_store(store_type, self._test_indexing_library)

    @ddt.data(*WORKS_WITH_STORES)
    def test_updating_item(self, store_type):
        self._perform_test_using_store(store_type, self._test_updating_item)

    @ddt.data(*WORKS_WITH_STORES)
    def test_creating_item(self, store_type):
        self._perform_test_using_store(store_type, self._test_creating_item)

    @ddt.data(*WORKS_WITH_STORES)
    def test_deleting_item(self, store_type):
        self._perform_test_using_store(store_type, self._test_deleting_item)

    @ddt.data(*WORKS_WITH_STORES)
    def test_not_indexable(self, store_type):
        self._perform_test_using_store(store_type, self._test_not_indexable)

    @ddt.data(*WORKS_WITH_STORES)
    def test_search_disabled(self, store_type):
        self._perform_test_using_store(store_type, self._test_search_disabled)

    @ddt.data(*WORKS_WITH_STORES)
    def test_exception(self, store_type):
        self._perform_test_using_store(store_type, self._test_exception)
