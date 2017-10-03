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
                if (!(ext.$autostart_period_days.attr("disabled"))){
                    sendData['autostart_period_days'] = ext.$autostart_period_days.val();
                }
                return $.ajax({
                    type: 'POST',
                    dataType: 'json',
                    url: ext.$settings_submit.data('endpoint'),
                    data: sendData,
                    success: function(data) {
                        ext.render_shift_view();
                        return ext.display_response('course-shifts-settings-editor', data);
                    },
                    error: function(xhr) {
                        return ext.fail_with_error('course-shifts-settings-editor', 'Error changing settings', xhr);
                    }
                });
            });

            this.autostart_change = function (){
                var value = ext.$is_autostart.filter(":checked").val();
                if (value.includes("True")){
                    ext.$autostart_period_days.val(ext.$autostart_period_days.data('default-value'));
                    ext.$autostart_period_days.attr("disabled", false);
                }
                if (value.includes("False")){
                    ext.$autostart_period_days.val(null);
                    ext.$autostart_period_days.attr("disabled", true);
                }
            };
            this.$is_autostart.change(this.autostart_change);
            this.$course_shifts_view = ext.$section.find('#course-shifts-view');
            this.create_shift_code = 'create-new-shift';
            this.autostart_change();
            this.render_shift_view();
        }

        course_shifts.prototype.render_shift_view = function() {
            var ext = this;
            if (ext.$is_autostart.filter(":checked").val().includes("True")){
                ext.$course_shifts_view.html('');
                return
            }
            var render = function (data) {
                var rendered_shifts = edx.HtmlUtils.template($('#course-shifts-detail-tpl').text())({
                    shifts_list: data
                });
                var template_place = ext.$course_shifts_view.find("#course-shifts-view-template");
                template_place.html(rendered_shifts["text"]);
                var select_shift = ext.$section.find("#shift-select");
                select_shift.change(function () {
                    ext.render_shift(this.value);
                });

                ext.render_shift(select_shift.val());

                ext.$submit_shift_view_button = ext.$course_shifts_view.find("#change-create-shift-button");
                var shift_view_submit_clicked = function() {
                    var name = ext.$course_shifts_view.find("input[name='course-shift-name']").attr("value");
                    var date = ext.$course_shifts_view.find("input[name='course-shift-date']").attr("value");
                    var select = ext.$course_shifts_view.find("#shift-select").val();
                    if (select.includes(ext.create_shift_code)) {
                        data = {};
                        if (name) {
                            data["name"] = name;
                        }
                        if (date) {
                            data["start_date"] = date;
                        }
                        return $.ajax({
                            type: 'POST',
                            dataType: 'json',
                            url: ext.$course_shifts_view.data('url-detail'),
                            data: data,
                            success: function (data) {
                                ext.render_shift_view();
                                ext.display_response('course-shifts-view', data);
                            },
                            error: function (xhr) {
                                return ext.fail_with_error('course-shifts-view', 'Error creating shift', xhr);
                            }
                        });
                    }
                    else {
                        data = {};
                        data["name"] = select;
                        if (name) {
                            data["new_name"] = name;
                        }
                        if (date) {
                            data["new_start_date"] = date;
                        }
                        return $.ajax({
                            type: 'PATCH',
                            dataType: 'json',
                            url: ext.$course_shifts_view.data('url-detail'),
                            data: data,
                            success: function (data) {
                                ext.render_shift_view();
                                ext.display_response('course-shifts-view', data);

                            },
                            error: function (xhr) {
                                return ext.fail_with_error('course-shifts-view', 'Error updating shift info', xhr);
                            }
                        });
                    }
                };
                ext.$submit_shift_view_button.click(shift_view_submit_clicked);

                ext.$delete_shift_button = ext.$course_shifts_view.find("#delete-shift-button");
                ext.$delete_shift_button.click(function () {
                    ext.clear_display();
                    var select = ext.$course_shifts_view.find("#shift-select").val();
                    if (select.includes(ext.create_shift_code)){
                        return
                    }
                    data = {"name":select};
                    return $.ajax({
                        type: 'DELETE',
                        dataType: 'json',
                        url: ext.$course_shifts_view.data('url-detail'),
                        data: data,
                        success: function (data) {
                            ext.render_shift_view();
                            ext.display_response('course-shifts-view', data);
                        },
                        error: function (xhr) {
                            return ext.fail_with_error('course-shifts-view', 'Error deleting shift', xhr);
                        }
                    })
                });

                ext.$user_add_button= ext.$course_shifts_view.find("#course-shift-add-user-button");
                ext.$user_add_button.click(function () {
                    ext.clear_display();
                    var select_value = ext.$course_shifts_view.find("#shift-select").val();
                    if (select_value.includes(ext.create_shift_code)){
                        return
                    }
                    var username_add = ext.$course_shifts_view.find("input[name='course-shift-username-add']");
                    var data = {
                        shift_name:select_value,
                        username:username_add.attr("value")
                    };

                    return $.ajax({
                        type: 'POST',
                        dataType: 'json',
                        url: ext.$course_shifts_view.data('url-membership'),
                        data: data,
                        success: function (data) {
                            ext.render_shift_view();
                            ext.display_response('course-shifts-view', data);
                        },
                        error: function (xhr) {
                            return ext.fail_with_error('course-shifts-view', 'Error adding user', xhr);
                        }
                    })
                });
                ext.clear_display();
            };

            return $.ajax({
                type: 'GET',
                dataType: 'json',
                url: this.$course_shifts_view.data('url-list'),
                success: function(data) {
                    return render(data);
                },
                error: function(xhr) {
                    return render([]);
                }
            });
        };

        course_shifts.prototype.render_shift = function(name){
            var ext = this;
            ext.clear_display();
            var render_shift_info = function(data){
                var name_field = ext.$course_shifts_view.find("input[name='course-shift-name']");
                var date_field = ext.$course_shifts_view.find("input[name='course-shift-date']");
                var enroll_start_field = ext.$course_shifts_view.find("#current-shift-enrollement-start");
                var enroll_finish_field = ext.$course_shifts_view.find("#current-shift-enrollement-finish");
                var users_count = ext.$course_shifts_view.find("#current-shift-users-count");
                var create_shift_disable = ext.$course_shifts_view.find(".create-shift-disable");
                if ($.isEmptyObject(data)){
                    name_field.attr("value", '');
                    date_field.attr("value", '');
                    enroll_start_field.html('');
                    enroll_finish_field.html('');
                    users_count.html('');
                    create_shift_disable.attr("disabled", true);
                    return;
                }
                name_field.attr("value", data["name"]);
                date_field.attr("value", data["start_date"]);
                enroll_start_field.html(data["enroll_start"]);
                enroll_finish_field.html(data["enroll_finish"]);
                users_count.html(data["users_count"]);
                if (create_shift_disable.attr("disabled")){
                    create_shift_disable.attr("disabled", false);
                }
            };
            if (name.includes(ext.create_shift_code)){
                render_shift_info({});
                return;
            }
            var data = {"name": name};
            return $.ajax({
                type: 'GET',
                dataType: 'json',
                url: this.$course_shifts_view.data('url-detail'),
                data:data,
                success: function(data) {
                    render_shift_info(data);
                },
                error: function(xhr) {
                    return ext.fail_with_error('course-shifts', 'Error getting shift data', xhr);
                }
            });
        };

        course_shifts.prototype.shift_view_submit_clicked = function (ext) {

        };

        course_shifts.prototype.clear_display = function() {
            this.$section.find('.request-response-error').empty().hide();
            return this.$section.find('.request-response').empty().hide();
        };

        course_shifts.prototype.display_response = function(id, data) {
            var $taskError, $taskResponse;
            $taskError = this.$section.find('#' + id + ' .request-response-error');
            $taskResponse = this.$section.find('#' + id + ' .request-response');
            $taskError.empty().hide();
            if ($.isEmptyObject(data)){
                data = "Success.";
            }
            var message = data;
            $taskResponse.empty().text(message);
            return $taskResponse.show();
        };

        course_shifts.prototype.fail_with_error = function(id, msg, xhr) {
            var $taskError, $taskResponse, data,
                message = msg;
            $taskError = this.$section.find('#' + id + ' .request-response-error');
            $taskResponse = this.$section.find('#' + id + ' .request-response');
            this.clear_display();
            data = $.parseJSON(xhr.responseText);

            var error_message = data.error;
            if ($.type(error_message) != 'string'){
                error_message = '';
                for (var key in data.error){
                    error_message += key + ":" +data.error[key] +";";
                }
            }
            message += ': ' + error_message;
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
