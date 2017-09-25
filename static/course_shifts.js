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
                var sendData;
                ext.clear_display();
                sendData = {
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

            var autostart_change = function (){
                var value = ext.$is_autostart.filter(":checked").val();
                if (value == "True"){
                    ext.$autostart_period_days.attr("disabled", false);
                }
                if (value == "False"){
                    ext.$autostart_period_days.val(null);
                    ext.$autostart_period_days.attr("disabled", true);
                }
            };
            autostart_change();
            this.$is_autostart.change(autostart_change);
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
