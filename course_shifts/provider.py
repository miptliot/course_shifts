from lms.djangoapps.courseware.field_overrides import FieldOverrideProvider

from .manager import CourseShiftManager


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
        return False

    def get(self, block, name, default):
        if not self.should_shift(block, name):
            return default
        course_key = block.location.course_key
        shift_manager = CourseShiftManager(course_key)

        if not shift_manager.is_enabled:
            return default
        shift_group = shift_manager.get_user_shift(self.user)
        if not shift_group:
            return default
        base_value = get_default_fallback_field_value(block, name)
        if base_value:
            shifted_value = shift_group.get_shifted_date(self.user, base_value)
            return shifted_value
        return default

    @classmethod
    def enabled_for(cls, course):
        """This simple override provider is always enabled"""
        return True


def get_default_fallback_field_value(block, name):
    """
    This function returns value of block's field
    avoiding recursive entering into the shift provider.
    """
    fallback = block._field_data._authored_data._source.fallback
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
