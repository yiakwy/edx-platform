(function (undefined) {
    describe('Video Accessible Menu', function () {
        var state;

        afterEach(function () {
            $('source').remove();
            state.storage.clear();
        });

        describe('constructor', function () {
            describe('always', function () {
                var videoTracks, container, button, menu, menuItems,
                    menuItemsLinks;

                beforeEach(function () {
                    state = jasmine.initializePlayer();
                    videoTracks = $('.video-tracks');
                    container = videoTracks.children('.wrapper-more-actions');
                    button = container.children('.has-dropdown');
                    menuList = container.children('.dropdown');
                    menuItems = menuList.children('.dropdown-item');
                    menuItemsLinks = menuItems.children('.action');
                });

                it('add the accessible menu', function () {
                    var activeMenuItem;
                    // Make sure we have the expected HTML structure:
                    // Menu container exists
                    expect(container.length).toBe(1);
                    // Only one button and one menu list per menu container.
                    expect(button.length).toBe(1);
                    expect(menuList.length).toBe(1);
                    // At least one menu item and one menu link per menu
                    // container. Exact length test?
                    expect(menuItems.length).toBeGreaterThan(0);
                    expect(menuItemsLinks.length).toBeGreaterThan(0);
                    expect(menuItems.length).toBe(menuItemsLinks.length);
                    // And one menu item is active
                    activeMenuItem = menuItems.filter('.active');
                    expect(activeMenuItem.length).toBe(1);

                    expect(activeMenuItem.children('.action'))
                        .toHaveData('value', 'srt');

                    // expect(activeMenuItem.children('.action'))
                    //     .toHaveHtml('SubRip (.srt) file');

                    /* TO DO: Check that all the anchors contain correct text.
                    $.each(li.toArray().reverse(), function (index, link) {
                        expect($(link)).toHaveData(
                            'speed', state.videoSpeedControl.speeds[index]
                        );
                        expect($(link).find('a').text()).toBe(
                            state.videoSpeedControl.speeds[index] + 'x'
                        );
                    });
                    */
                });

                it('add ARIA attributes to button, menu, and menu items links',
                   function () {
                    expect(button).toHaveAttrs({
                        'aria-disabled': 'false',
                        'aria-haspopup': 'true',
                        'aria-expanded': 'false'
                    });

                    menuItemsLinks.each(function(){
                        expect($(this)).toHaveAttrs({
                            'aria-disabled': 'false'
                        });
                    });
                });
            });

            describe('when running', function () {
                var videoTracks, container, button, menu, menuItems,
                    menuItemsLinks, KEY = $.ui.keyCode,

                    keyPressEvent = function(key) {
                        return $.Event('keydown', {keyCode: key});
                    },

                    tabBackPressEvent = function() {
                        return $.Event('keydown',
                                       {keyCode: KEY.TAB, shiftKey: true});
                    },

                    tabForwardPressEvent = function() {
                        return $.Event('keydown',
                                       {keyCode: KEY.TAB, shiftKey: false});
                    },

                    // Get previous element in array or cyles back to the last
                    // if it is the first.
                    previousSpeed = function(index) {
                        return speedEntries.eq(index < 1 ?
                                               speedEntries.length - 1 :
                                               index - 1);
                    },

                    // Get next element in array or cyles back to the first if
                    // it is the last.
                    nextSpeed = function(index) {
                        return speedEntries.eq(index >= speedEntries.length-1 ?
                                               0 :
                                               index + 1);
                    };

                beforeEach(function () {
                    state = jasmine.initializePlayer();
                    videoTracks = $('.video-tracks');
                    container = videoTracks.children('.wrapper-more-actions');
                    button = container.children('.button-more.has-dropdown');
                    menuList = container.children('.dropdown');
                    menuItems = menuList.children('.dropdown-item');
                    menuItemsLinks = menuItems.children('.action');
                    spyOn($.fn, 'focus').andCallThrough();
                });

                it('open the menu on click', function () {
                    button.click();
                    expect(button).toHaveClass('is-active');
                    expect(menuList).toHaveClass('is-visible');
                });

                if('close the menu on outside click', function() {
                    $(window).click();
                    expect(menuList).not.toHaveClass('is-visible');
                });
            });
        });

        // TODO
        xdescribe('change file format', function () {
            describe('when new file format is not the same', function () {
                beforeEach(function () {
                    state = jasmine.initializePlayer();
                    state.videoSpeedControl.setSpeed(1.0);
                    spyOn(state.videoPlayer, 'onSpeedChange').andCallThrough();

                    $('li[data-speed="0.75"] a').click();
                });

                it('trigger speedChange event', function () {
                    expect(state.videoPlayer.onSpeedChange).toHaveBeenCalled();
                    expect(state.videoSpeedControl.currentSpeed).toEqual(0.75);
                });
            });
        });

        // TODO
        xdescribe('onSpeedChange', function () {
            beforeEach(function () {
                state = jasmine.initializePlayer();
                $('li[data-speed="1.0"] a').addClass('active');
                state.videoSpeedControl.setSpeed(0.75);
            });

            it('set the new speed as active', function () {
                expect($('.video_speeds li[data-speed="1.0"]'))
                    .not.toHaveClass('active');
                expect($('.video_speeds li[data-speed="0.75"]'))
                    .toHaveClass('active');
                expect($('.speeds p.active')).toHaveHtml('0.75x');
            });
        });
    });
}).call(this);
