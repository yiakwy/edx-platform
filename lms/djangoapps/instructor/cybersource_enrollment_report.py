"""
Defines concrete class for cybersource  Enrollment Report.

"""
from instructor.enrollment_report import BaseEnrollmentReportProvider


class CyberSourceEnrollmentReportProvider(BaseEnrollmentReportProvider):
    """
    The concrete class for all CyberSource Enrollment Reports.
    """

    def get_enrollment_info(self, user_id, course_id):
        """
        Returns the User Enrollment information.
        """
        pass

    def get_payment_info(self, user_id, course_id):
        """
        Returns the User Payment information.
        """
        pass
