/* globals _ */

(function() {
    'use strict';
    var CourseShifts;

    CourseShifts = (function() {
        function course_shifts($section) {
            var ext = this;
            this.$section = $section;
            this.$section.data('wrapper', this);

            this.$enroll_after_days = this.$section.find("input[name='enroll-after-days']");
            this.$enroll_before_days = this.$section.find("input[name='enroll-before-days']");
            this.$autostart_period_days = this.$section.find("input[name='autostart-period-days']");
            this.$is_autostart = this.$section.find("input[name='is-autostart']");
            this.$settings_submit = this.$section.find("input[name='settings-submit']");

            this.$section.find('.request-response').hide();
            this.$section.find('.request-response-error').hide();

            this.$settings_submit.click(function() {
                ext.clear_display();
                var sendData = {
                    enroll_after_days: ext.$enroll_after_days.val(),
                    enroll_before_days: ext.$enroll_before_days.val(),
                    is_autostart: ext.$is_autostart.filter(":checked").val()
                };
                if (ext.$autostart_period_days){
                    sendData['autostart_period_days'] = ext.$autostart_period_days.val();
                }
                return $.ajax({
                    type: 'POST',
                    dataType: 'json',
                    url: ext.$settings_submit.data('endpoint'),
                    data: sendData,
                    success: function(data) {
                        return ext.display_response('course-shifts', data);
                    },
                    error: function(xhr) {
                        return ext.fail_with_error('course-shifts', 'Error changing settings', xhr);
                    }
                });
            });

            this.autostart_change = function (){
                var value = ext.$is_autostart.filter(":checked").val();
                if (value == "True"){
                    ext.$autostart_period_days.attr("disabled", false);
                }
                if (value == "False"){
                    ext.$autostart_period_days.val(null);
                    ext.$autostart_period_days.attr("disabled", true);
                }
            };
            this.autostart_change();
            this.$is_autostart.change(this.autostart_change);
            this.$course_shifts_view = ext.$section.find('#course-shifts-view');

            this.get_shift_list = function(handle){
                return $.ajax({
                    type: 'GET',
                    dataType: 'json',
                    url: this.$course_shifts_view.data('url-list'),
                    success: function(data) {
                        return handle(data);
                    },
                    error: function(xhr) {
                        return handle([]);
                    }
                });
            };

            this.render_list = function() {
                this.get_shift_list(function (data) {
                    var rendered_shifts = edx.HtmlUtils.template($('#course-shifts-detail-tpl').text())({
                        shifts_list: data
                    });
                    ext.$course_shifts_view.html(rendered_shifts["text"]);
                    var select_shift = ext.$section.find("#shift-select");
                    select_shift.change(function () {
                        ext.render_shift(this.value);
                    })
                });
            };

            this.render_shift_info = function(data){
                var name_field = ext.$course_shifts_view.find("input[name='course-shift-name']");
                var date_field = ext.$course_shifts_view.find("input[name='course-shift-date']");
                var enroll_start_field = ext.$course_shifts_view.find("#current-shift-enrollement-start");
                var enroll_finish_field = ext.$course_shifts_view.find("#current-shift-enrollement-finish");
                var users_count = ext.$course_shifts_view.find("#current-shift-users-count");
                if ($.isEmptyObject(data)){
                    name_field.attr("value", '');
                    date_field.attr("value", '');
                    enroll_start_field.html('');
                    enroll_finish_field.html('');
                    users_count.html('');
                    return;
                }
                name_field.attr("value", data["name"]);
                date_field.attr("value", data["start_date"]);
                enroll_start_field.html(data["enroll_start"]);
                enroll_finish_field.html(data["enroll_finish"]);
                users_count.html(data["users_count"]);
            };

            this.render_shift = function(name){

                if (name.includes("create-new-shift")){
                    ext.render_shift_info({});
                    return;
                }
                var data = {"name": name};
                return $.ajax({
                    type: 'GET',
                    dataType: 'json',
                    url: this.$course_shifts_view.data('url-detail'),
                    data:data,
                    success: function(data) {
                        ext.render_shift_info(data);
                    },
                    error: function(xhr) {
                        return ext.fail_with_error('course-shifts', 'Error getting shift data', xhr);
                    }
                });
            };


            this.render_list();

        }

        course_shifts.prototype.clear_display = function() {
            this.$section.find('.request-response-error').empty().hide();
            return this.$section.find('.request-response').empty().hide();
        };

        course_shifts.prototype.display_response = function(id, data) {
            var $taskError, $taskResponse;
            $taskError = this.$section.find('#' + id + ' .request-response-error');
            $taskResponse = this.$section.find('#' + id + ' .request-response');
            $taskError.empty().hide();
            if (!data){
                data = "Success.";
            }
            $taskResponse.empty().text(data);
            return $taskResponse.show();
        };

        course_shifts.prototype.fail_with_error = function(id, msg, xhr) {
            var $taskError, $taskResponse, data,
                message = msg;
            $taskError = this.$section.find('#' + id + ' .request-response-error');
            $taskResponse = this.$section.find('#' + id + ' .request-response');
            this.clear_display();
            data = $.parseJSON(xhr.responseText);
            message += ': ' + data.error;
            $taskResponse.empty();
            $taskError.empty();
            $taskError.text(message);
            return $taskError.show();
        };

        course_shifts.prototype.onClickTitle = function() {};

        return course_shifts;
    }());

    _.defaults(window, {
        InstructorDashboard: {}
    });

    _.defaults(window.InstructorDashboard, {
        sections: {}
    });

    _.defaults(window.InstructorDashboard.sections, {
        CourseShifts: CourseShifts
    });
}).call(this);
