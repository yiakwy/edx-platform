"""
Test course discovery.
"""
import datetime
import json
import os

from bok_choy.web_app_test import WebAppTest
from ...pages.common.logout import LogoutPage
from ...pages.studio.auto_auth import AutoAuthPage
from ...pages.lms.discovery import CourseDiscoveryPage
from ...fixtures.course import CourseFixture

class CourseDiscoveryTest(WebAppTest):
    """
    Test searching for courses.
    """

    STAFF_USERNAME = "STAFF_TESTER"
    STAFF_EMAIL = "staff101@example.com"
    TEST_INDEX_FILENAME = "test_root/index_file.dat"

    def setUp(self):
        """
        Create course page and courses to find
        """
        # create index file
        with open(self.TEST_INDEX_FILENAME, "w+") as index_file:
            json.dump({}, index_file)

        super(CourseDiscoveryTest, self).setUp()
        self.page = CourseDiscoveryPage(self.browser)

        for i in range(10):
            org = self.unique_id
            number = unicode(i)
            run = "test_run"
            name = "test course"
            settings = {'enrollment_start': datetime.datetime(1970, 1, 1).isoformat()}
            CourseFixture(org, number, run, name, settings=settings).install()

        for i in range(2):
            org = self.unique_id
            number = unicode(i)
            run = "test_run"
            name = "grass is always greener"
            CourseFixture(org, number, run, name, settings={'enrollment_start': datetime.datetime(1970, 1, 1).isoformat()}).install()


    def tearDown(self):
        os.remove(self.TEST_INDEX_FILENAME)

    def _auto_auth(self, username, email, staff):
        """
        Logout and login with given credentials.
        """
        LogoutPage(self.browser).visit()
        AutoAuthPage(self.browser, username=username, email=email, staff=staff).visit()

    def test_page_existence(self):
        """
        Make sure that the page is accessible.
        """
        self.page.visit()

    def test_search(self):
        """
        Make sure you can search for courses.
        """
        self.page.visit()
        self.assertEqual(len(self.page.result_items), 12)

        self.page.search("grass")
        self.assertEqual(len(self.page.result_items), 2)

        self.page.clear_search()
        self.assertEqual(len(self.page.result_items), 12)
