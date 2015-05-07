"""
Defines abstract class for the Enrollment Reports.
"""
from instructor.enrollment_report_provider import EnrollmentReportProvider
from django.contrib.auth.models import User


class BaseEnrollmentReportProvider(EnrollmentReportProvider):
    """
    The base abstract class for all Enrollment Reports that can support multiple
    backend such as MySQL/Django-ORM.

    # don't allow instantiation of this class, it must be subclassed
    """
    def get_user_profile(self, user_id):
        """
        Returns the UserProfile information.
        """
        return User.objects.select_related('profile').get(id=user_id)

    def get_enrollment_info(self, user_id, course_id):
        """
        Returns the User Enrollment information.
        """
        raise NotImplementedError()

    def get_payment_info(self, user_id, course_id):
        """
        Returns the User Payment information.
        """
        raise NotImplementedError()
