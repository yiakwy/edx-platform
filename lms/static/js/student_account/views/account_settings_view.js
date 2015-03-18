;(function (define, undefined) {
    'use strict';
    define([
        'gettext', 'jquery', 'underscore', 'backbone',
    ], function (gettext, $, _, Backbone) {

        var AccountSettingsView = Backbone.View.extend({

            initialize: function (options) {
                this.template = _.template($('#account_settings-tpl').text());
                _.bindAll(this, 'render', 'renderFields');
            },

            render: function () {
                this.$el.html(this.template({
                    sections: this.options.sections
                }));
                return this;
            },

            renderFields: function () {
                this.$('.ui-loading-indicator').addClass('is-hidden');

                var view = this;
                _.each(this.$('.account-settings-section-body'), function (sectionEl, index) {
                    _.each(view.options.sections[index].fields, function (field, index) {
                        $(sectionEl).append(field.view.render().el);
                    });
                });
                return this;
            }
        });

        return AccountSettingsView;
    })
}).call(this, define || RequireJS.define);