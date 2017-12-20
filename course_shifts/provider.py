import datetime
import dateutil.parser
import logging
from lms.djangoapps.courseware.field_overrides import FieldOverrideProvider

from .manager import CourseShiftManager

log = logging.getLogger(__name__)


class CourseShiftOverrideProvider(FieldOverrideProvider):
    """
    This override provider shifts due dates for courseware
    based on user's membership in CourseShiftGroups
    """

    COURSE_OVERRIDEN_NAMES = (
        'due',
    )
    BLOCK_OVERRIDEN_NAMES = (
        'due',
        'start'
    )
    BLOCK_OVERRIDEN_CATEGORIES = (
        'chapter',
        'sequential',
        'vertical',
    )
    OPENASSESSMENT_NAMES = (
        'due',
        'submission_due'
        'start',
        'submission_start',
        'rubric_assessments'
    )

    def should_shift(self, block, name):
        """
        Defines when to shift(override) field value
        """
        category = block.category
        if category == 'course':
            if name in self.COURSE_OVERRIDEN_NAMES:
                return True
        if category in self.BLOCK_OVERRIDEN_CATEGORIES:
            if name in self.BLOCK_OVERRIDEN_NAMES:
                return True
        if category == 'openassessment':
            if name in self.OPENASSESSMENT_NAMES:
                return True
        return False

    def get(self, block, name, default):
        if not self.should_shift(block, name):
            return default
        if unicode(self.user) == u'SystemUser':
            return default
        course_key = block.location.course_key
        shift_manager = CourseShiftManager(course_key)

        if not shift_manager.is_enabled:
            return default
        shift_group = shift_manager.get_user_shift(self.user)
        if not shift_group:
            return default
        base_value = get_default_fallback_field_value(block, name)

        if not base_value:
            return default

        if isinstance(base_value, datetime.datetime):
            shifted_value = shift_group.get_shifted_date(self.user, base_value)
            return shifted_value
        elif isinstance(base_value, basestring):
            shifted_string_value = self.shift_string_date(
                base_value=base_value,
                shift_group=shift_group,
                name=name
            )
            if shifted_string_value is None:
                return default
            return shifted_string_value
        elif isinstance(base_value, list):
            if name != 'rubric_assessments':
                log.error("CourseShift can't move list of dates other than 'rubric_assessments': {} ({})".format(
                    base_value,
                    name
                ))
                return default
            shifted_rubric_assessments = self.shift_rubric_assessment(
                base_value=base_value,
                shift_group=shift_group,
                name=name
            )
            if shifted_rubric_assessments is None:
                return default
            return shifted_rubric_assessments
        else:
            log.error("CourseShift can't move field '{}' with type {}".format(
                name,
                type(base_value)
            ))
            return default

    @classmethod
    def enabled_for(cls, course):
        """This simple override provider is always enabled"""
        return True

    def shift_string_date(self, base_value, shift_group, name):
        parsed_value = dateutil.parser.parse(base_value)
        if parsed_value.isoformat() != base_value:
            log.error("CourseShift can't move non-iso 8601 date: {} ({})".format(
                base_value,
                name
            ))
            return None
        shifted_value = shift_group.get_shifted_date(self.user, parsed_value)
        return shifted_value.isoformat()

    def shift_rubric_assessment(self, base_value, shift_group, name):
        shifted_rubric_assessment = []
        for row in base_value:
            shifted_start = self.shift_string_date(
                base_value=row['start'],
                shift_group=shift_group,
                name=name
            )
            shifted_due = self.shift_string_date(
                base_value=row['due'],
                shift_group=shift_group,
                name=name
            )
            if (shifted_due is None) or (shifted_start is None):
                return
            shifted_row = dict(row)
            shifted_row['start'] = shifted_start
            shifted_row['due'] = shifted_due
            shifted_rubric_assessment.append(shifted_row)
        return shifted_rubric_assessment


def get_default_fallback_field_value(block, name):
    """
    This function returns value of block's field
    avoiding recursive entering into the shift provider.
    """
    try: # we have LmsFieldData in block during rendering
        fallback = block._field_data._authored_data._source.fallback
    except AttributeError: #we have Kvs or InheritingFieldData in block
        fallback = block._field_data
    base_value = None
    if fallback.has(block, name):
        base_value = fallback.get(block, name)
    return base_value


def _get_default_scoped_field_value(block, name):
    """
    This function returns value of block's field
    avoiding recursive entering into the shift provider.
    """
    # This is a bit more hacky way to get base value.
    # It is slower and stranger than the one with fallback
    safe_scope_names = ("preferences", "user_info")
    scope_field_data_dict = block._field_data._scope_mappings
    scope_name_dict = dict((x.name, x) for x in scope_field_data_dict.keys())

    for scope_name in safe_scope_names:
        scope = scope_name_dict.get(scope_name)
        if not scope:
            continue
        field_data = scope_field_data_dict.get(scope)
        if field_data.has(block, name):
            return field_data.get(block, name)
