define([
    'jquery',
    'sinon',
    'backbone',
    'logger',
    'js/common_helpers/template_helpers',
    'js/discovery/app',
    'js/discovery/collection',
    'js/discovery/form',
    'js/discovery/result',
    'js/discovery/result_item_view',
    'js/discovery/result_list_view',
    'js/discovery/filter',
    'js/discovery/filters',
    'js/discovery/filter_bar_view',
    'js/discovery/filter_view',
    'js/discovery/search_facets_view'
], function(
    $,
    Sinon,
    Backbone,
    Logger,
    TemplateHelpers,
    App,
    Collection,
    DiscoveryForm,
    ResultItem,
    ResultItemView,
    ResultListView,
    FilterModel,
    FiltersCollection,
    FiltersBarView,
    FilterView,
    SearchFacetView
) {
    'use strict';

    var JSON_RESPONSE = {
        "total": 365,
        "results": [
            {
                "data": {
                    "modes": [
                        "honor"
                    ],
                    "course": "edX/DemoX/Demo_Course",
                    "enrollment_start": "2015-04-21T00:00:00+00:00",
                    "number": "DemoX",
                    "content": {
                        "overview": " About This Course Include your long course description here.",
                        "display_name": "edX Demonstration Course",
                        "number": "DemoX"
                    },
                    "start": "1970-01-01T05:00:00+00:00",
                    "image_url": "/c4x/edX/DemoX/asset/images_course_image.jpg",
                    "org": "edX",
                    "id": "edX/DemoX/Demo_Course"
                }
            }
        ]
    };

    var FACET_LIST = [
        {"type": "example1", "query": "search1"},
        {"type": "example2", "query": "search2"}
    ];

    var SEARCH_FILTER = {"type": "search_string", "query": "search3"};



    describe('Collection', function () {

        beforeEach(function () {
            this.server = Sinon.fakeServer.create();
            this.collection = new Collection();

            this.onSearch = jasmine.createSpy('onSearch');
            this.collection.on('search', this.onSearch);

            this.onNext = jasmine.createSpy('onNext');
            this.collection.on('next', this.onNext);

            this.onError = jasmine.createSpy('onError');
            this.collection.on('error', this.onError);
        });

        afterEach(function () {
            this.server.restore();
        });

        it('sends a request and parses the json result', function () {
            this.collection.performSearch('search string');
            this.server.respondWith('POST', this.collection.url, [200, {}, JSON.stringify(JSON_RESPONSE)]);
            this.server.respond();

            expect(this.onSearch).toHaveBeenCalled();
            expect(this.collection.totalCount).toEqual(365);
            expect(this.collection.latestModels()[0].attributes).toEqual(JSON_RESPONSE.results[0].data);
            expect(this.collection.page).toEqual(0);
        });

        it('handles errors', function () {
            this.collection.performSearch('search string');
            this.server.respond();
            expect(this.onSearch).not.toHaveBeenCalled();
            expect(this.onError).toHaveBeenCalled();
            this.collection.loadNextPage();
            this.server.respond();
            expect(this.onSearch).not.toHaveBeenCalled();
            expect(this.onError).toHaveBeenCalled();
        });

        it('loads next page', function () {
            var response = { total: 35, results: [] };
            this.collection.loadNextPage();
            this.server.respond('POST', this.collection.url, [200, {}, JSON.stringify(response)]);
            expect(this.onNext).toHaveBeenCalled();
            expect(this.onError).not.toHaveBeenCalled();
        });

        it('sends correct paging parameters', function () {
            this.collection.performSearch('search string');
            var response = { total: 52, results: [] };
            this.server.respondWith('POST', this.collection.url, [200, {}, JSON.stringify(response)]);
            this.server.respond();
            this.collection.loadNextPage();
            this.server.respond();
            spyOn($, 'ajax');
            this.collection.loadNextPage();
            expect($.ajax.mostRecentCall.args[0].url).toEqual(this.collection.url);
            expect($.ajax.mostRecentCall.args[0].data).toEqual({
                search_string : 'search string',
                page_size : this.collection.pageSize,
                page_index : 2
            });
        });

        it('has next page', function () {
            var response = { total: 35, access_denied_count: 5, results: [] };
            this.collection.performSearch('search string');
            this.server.respond('POST', this.collection.url, [200, {}, JSON.stringify(response)]);
            expect(this.collection.hasNextPage()).toEqual(true);
            this.collection.loadNextPage();
            this.server.respond();
            expect(this.collection.hasNextPage()).toEqual(false);
        });

        it('resets state when performing new search', function () {
            this.collection.add(new ResultItem());
            expect(this.collection.length).toEqual(1);
            this.collection.performSearch('search string');
            expect(this.collection.length).toEqual(0);
            expect(this.collection.page).toEqual(0);
            expect(this.collection.totalCount).toEqual(0);
            expect(this.collection.latestModelsCount).toEqual(0);
        });

    });


    describe('ResultItem', function () {

        beforeEach(function () {
            this.result = new ResultItem();
        });

        it('has properties', function () {
            expect(this.result.get('modes')).toBeDefined();
            expect(this.result.get('course')).toBeDefined();
            expect(this.result.get('enrollment_start')).toBeDefined();
            expect(this.result.get('number')).toBeDefined();
            expect(this.result.get('content')).toEqual({
                display_name: '',
                number: '',
                overview: ''
            });
            expect(this.result.get('start')).toBeDefined();
            expect(this.result.get('image_url')).toBeDefined();
            expect(this.result.get('org')).toBeDefined();
            expect(this.result.get('id')).toBeDefined();
        });

    });


    describe('ResultItemView', function () {

        beforeEach(function () {
            TemplateHelpers.installTemplate('templates/discovery/result_item');
            this.item = new ResultItemView({
                model: new ResultItem(JSON_RESPONSE.results[0].data)
            });
        });

        it('renders correctly', function () {
            var data = this.item.model.attributes;
            this.item.render();
            expect(this.item.$el).toContainHtml(data.content.display_name);
            expect(this.item.$el).toContain('a[href="/courses/' + data.course + '/info"]');
            expect(this.item.$el).toContain('img[src="' + data.image_url + '"]');
            expect(this.item.$el.find('.course-name')).toContainHtml(data.org);
            expect(this.item.$el.find('.course-name')).toContainHtml(data.content.number);
            expect(this.item.$el.find('.course-name')).toContainHtml(data.content.display_name);
            expect(this.item.$el.find('.course-date')).toContainHtml('Jan 01, 1970');
        });

    });


    describe('DiscoveryForm', function () {

        beforeEach(function () {
            loadFixtures('js/fixtures/discovery.html');
            TemplateHelpers.installTemplates([
                'templates/discovery/not_found',
                'templates/discovery/error'
            ]);
            this.form = new DiscoveryForm();
            this.onSearch = jasmine.createSpy('onSearch');
            this.form.on('search', this.onSearch);
        });

        it('trims input string', function () {
            var term = '  search string  ';
            $('.discovery-input').val(term);
            $('form').trigger('submit');
            expect(this.onSearch).toHaveBeenCalledWith($.trim(term));
        });

        it('handles calls to doSearch', function () {
            var term = '  search string  ';
            $('.discovery-input').val(term);
            this.form.doSearch(term);
            expect(this.onSearch).toHaveBeenCalledWith($.trim(term));
            expect($('.discovery-input').val()).toEqual(term);
            expect($('#discovery-message')).toBeEmpty();
        });

        it('clears search', function () {
            $('.discovery-input').val('somethig');
            this.form.clearSearch();
            expect($('.discovery-input').val()).toEqual('');
        });

        it('shows/hides loading indicator', function () {
            this.form.showLoadingIndicator();
            expect($('#loading-indicator')).not.toHaveClass('hidden');
            this.form.hideLoadingIndicator();
            expect($('#loading-indicator')).toHaveClass('hidden');
        });

        it('shows messages', function () {
            this.form.showNotFoundMessage();
            expect($('#discovery-message')).not.toBeEmpty();
            this.form.showErrorMessage();
            expect($('#discovery-message')).not.toBeEmpty();
        });

    });

    describe('FilterBarView', function () {
        beforeEach(function () {
            loadFixtures('js/fixtures/discovery.html');
            TemplateHelpers.installTemplates(
                ['templates/discovery/filter_bar',
                'templates/discovery/filter']
            );
            this.filterBar = new FiltersBarView();
            this.onClear = jasmine.createSpy('onClear');
            this.filterBar.on('clear', this.onClear);
        });

        it('view searches for sent facet object', function () {
            expect(this.filterBar.$el.length).toBe(1);
            this.filterBar.addFilter(FACET_LIST[0]);
            expect(this.filterBar.$el.find('#clear-all-filters')).toBeVisible();
        });

        it('view searches for entered search string', function () {
            spyOn(this.filterBar, 'addFilter').andCallThrough();
            expect(this.filterBar.$el.length).toBe(1);
            this.filterBar.changeQueryFilter(SEARCH_FILTER.query);
            expect(this.filterBar.$el.find('#clear-all-filters')).toBeVisible();
            expect(this.filterBar.addFilter).toHaveBeenCalledWith(SEARCH_FILTER);
        });

        it('model cleans view on destruction correctly', function () {
            this.filterBar.addFilter(SEARCH_FILTER);
            var model = this.filterBar.collection.findWhere(SEARCH_FILTER);
            expect(this.filterBar.$el.find('.active-filter').length).toBe(1);
            model.cleanModelView();
            expect(this.filterBar.$el.find('.active-filter').length).toBe(0);
        });

        it('view removes all filters and hiddes bar if clear all', function () {
            spyOn(this.filterBar, 'clearAll').andCallThrough();
            this.filterBar.delegateEvents();
            this.filterBar.addFilter(SEARCH_FILTER);
            var clear_all = this.filterBar.$el.find('#clear-all-filters');
            expect(clear_all).toBeVisible();
            clear_all.trigger('click');
            expect(this.filterBar.clearAll).toHaveBeenCalled();
            expect(this.onClear).toHaveBeenCalled();
        });

        it('view hiddes bar if all filters removed', function () {
            spyOn(this.filterBar, 'clearFilter').andCallThrough();
            this.filterBar.delegateEvents();
            this.filterBar.addFilter(SEARCH_FILTER);
            var clear_all = this.filterBar.$el.find('#clear-all-filters');
            expect(clear_all).toBeVisible();
            var filter = this.filterBar.$el.find('li a');
            filter.trigger('click');
            expect(this.filterBar.clearFilter).toHaveBeenCalled();
            expect(this.onClear).toHaveBeenCalled();
        });

        it('view changes query filter', function () {
            this.filterBar.delegateEvents();
            this.filterBar.addFilter(SEARCH_FILTER);
            var filter = $(this.filterBar.$el.find('li a')[0]);
            expect(filter.text().trim()).toBe(SEARCH_FILTER.query);
            // Have to explicitly remove model because events not dispatched
            var model = this.filterBar.collection.findWhere(SEARCH_FILTER);
            model.cleanModelView();
            this.filterBar.changeQueryFilter(SEARCH_FILTER.query + '2');
            filter = $(this.filterBar.$el.find('li a')[0]);
            expect(filter.text().trim()).toBe(SEARCH_FILTER.query + '2');
        });

        it('view returns correct search term', function () {
            this.filterBar.delegateEvents();
            this.filterBar.addFilter(SEARCH_FILTER);
            expect(this.filterBar.getSearchTerm()).toBe(SEARCH_FILTER.query);
        });

    });

    describe('SearchFacetView', function () {
        beforeEach(function () {
            loadFixtures('js/fixtures/discovery.html');
            this.searchFacetView = new SearchFacetView();
            this.onAddFilter = jasmine.createSpy('onAddFilter');
            this.searchFacetView.on('addFilter', this.onAddFilter);
        });

        it('view expands more content on show more click', function () {
            this.searchFacetView.delegateEvents();
            var $show_more = this.searchFacetView.$el.find('.show-more');
            var $show_less = this.searchFacetView.$el.find('.show-less');
            var $ul = $show_more.parent('div').siblings('ul');
            expect($show_more).not.toHaveClass('hidden');
            expect($show_less).toHaveClass('hidden');
            expect($ul).toHaveClass('collapse');
            $show_more.trigger('click');
            expect($show_more).toHaveClass('hidden');
            expect($show_less).not.toHaveClass('hidden');
            expect($ul).not.toHaveClass('collapse');
        });

        it('view collapses content on show less click', function () {
            this.searchFacetView.delegateEvents();
            var $show_more = this.searchFacetView.$el.find('.show-more');
            var $show_less = this.searchFacetView.$el.find('.show-less');
            var $ul = $show_more.parent('div').siblings('ul');
            $show_more.trigger('click');
            expect($show_more).toHaveClass('hidden');
            expect($show_less).not.toHaveClass('hidden');
            expect($ul).not.toHaveClass('collapse');
            $show_less.trigger('click');
            expect($show_more).not.toHaveClass('hidden');
            expect($show_less).toHaveClass('hidden');
            expect($ul).toHaveClass('collapse');
        });

        it('view triggers addFilter event if facet is clicked', function () {
            this.searchFacetView.delegateEvents();
            var $facet_link = this.searchFacetView.$el.find('li a[data-value="Current"]');
            var $facet = $facet_link.parent('li');
            $facet.trigger('click');
            expect(this.onAddFilter).toHaveBeenCalledWith(
                {
                    type: $facet.data('facet'),
                    query: $facet_link.data('value')
                }
            );
        });

    });

    describe('ResultListView', function () {

        beforeEach(function () {
            jasmine.Clock.useMock();
            loadFixtures('js/fixtures/discovery.html');
            TemplateHelpers.installTemplates([
                'templates/discovery/result_item',
                'templates/discovery/not_found',
                'templates/discovery/error'
            ]);
            var collection = new Collection([JSON_RESPONSE.results[0].data]);
            collection.latestModelsCount = 1;
            this.view = new ResultListView({ collection: collection });
        });

        it('renders search results', function () {
            this.view.render();
            expect($('.courses-listing article').length).toEqual(1);
            expect($('.courses-listing .course-title')).toContainHtml('edX Demonstration Course');
            this.view.renderNext();
            expect($('.courses-listing article').length).toEqual(2);
        });

        it('scrolling triggers an event for next page', function () {
            this.onNext = jasmine.createSpy('onNext');
            this.view.on('next', this.onNext);
            spyOn(this.view.collection, 'hasNextPage').andCallFake(function () {
                return true;
            });
            this.view.render();
            window.scroll(0, $(document).height());
            $(window).trigger('scroll');
            jasmine.Clock.tick(500);
            expect(this.onNext).toHaveBeenCalled();

            // should not be triggered again (while it is loading)
            $(window).trigger('scroll');
            jasmine.Clock.tick(500);
            expect(this.onNext.calls.length).toEqual(1);
        });

    });


    describe('Discovery App', function () {

        beforeEach(function () {
            loadFixtures('js/fixtures/discovery.html');
            TemplateHelpers.installTemplates([
                'templates/discovery/result_item',
                'templates/discovery/filter',
                'templates/discovery/filter_bar',
                'templates/discovery/not_found',
                'templates/discovery/error'
            ]);
            this.server = Sinon.fakeServer.create();
            this.app = new App(
                Collection,
                DiscoveryForm,
                ResultListView,
                FiltersBarView,
                SearchFacetView
            );
        });

        afterEach(function () {
            this.server.restore();
        });

        it('performs search', function () {
            $('.discovery-input').val('test');
            $('.discovery-submit').trigger('click');
            this.server.respondWith('POST', '/search/course_discovery/', [200, {}, JSON.stringify(JSON_RESPONSE)]);
            this.server.respond();
            expect($('.courses-listing article').length).toEqual(1);
            expect($('.courses-listing .course-title')).toContainHtml('edX Demonstration Course');
            expect($('.active-filter').length).toBe(1);
        });

        it('loads more', function () {
            jasmine.Clock.useMock();
            $('.discovery-input').val('test');
            $('.discovery-submit').trigger('click');
            this.server.respondWith('POST', '/search/course_discovery/', [200, {}, JSON.stringify(JSON_RESPONSE)]);
            this.server.respond();
            expect($('.courses-listing article').length).toEqual(1);
            expect($('.courses-listing .course-title')).toContainHtml('edX Demonstration Course');
            window.scroll(0, $(document).height());
            $(window).trigger('scroll');
            jasmine.Clock.tick(500);
            this.server.respondWith('POST', '/search/course_discovery/', [200, {}, JSON.stringify(JSON_RESPONSE)]);
            this.server.respond();
            expect($('.courses-listing article').length).toEqual(2);
        });

        it('displays not found message', function () {
            $('.discovery-input').val('asdfasdf');
            $('.discovery-submit').trigger('click');
            this.server.respondWith('POST', '/search/course_discovery/', [200, {}, '{}']);
            this.server.respond();
            expect($('#discovery-message')).not.toBeEmpty();
            expect($('.courses-listing article').length).toEqual(1);
            expect($('.courses-listing .course-title')).toContainHtml('title');
        });

        it('displays error message', function () {
            $('.discovery-input').val('asdfasdf');
            $('.discovery-submit').trigger('click');
            this.server.respondWith('POST', '/search/course_discovery/', [404, {}, '']);
            this.server.respond();
            expect($('#discovery-message')).not.toBeEmpty();
            expect($('.courses-listing article').length).toEqual(1);
            expect($('.courses-listing .course-title')).toContainHtml('title');
        });

        it('check filters and bar removed on clear all', function () {
            $('.discovery-input').val('test');
            $('.discovery-submit').trigger('click');
            this.server.respondWith('POST', '/search/course_discovery/', [200, {}, JSON.stringify(JSON_RESPONSE)]);
            this.server.respond();
            expect($('.active-filter').length).toBe(1);
            expect($('#filter-bar')).not.toHaveClass('hidden');
            $('#clear-all-filters').trigger('click');
            expect($('.active-filter').length).toBe(0);
            expect($('#filter-bar')).toHaveClass('hidden');
        });

        it('check filters and bar removed on last filter cleared', function () {
            $('.discovery-input').val('test');
            $('.discovery-submit').trigger('click');
            this.server.respondWith('POST', '/search/course_discovery/', [200, {}, JSON.stringify(JSON_RESPONSE)]);
            this.server.respond();
            expect($('.active-filter').length).toBe(1);
            var $filter = $('.active-filter');
            $filter.find('a').trigger('click');
            expect($('.active-filter').length).toBe(0);
        });

    });



});
