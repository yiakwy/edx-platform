# -*- coding: utf-8 -*-
"""
Fake Software Secure page for use in acceptance tests.
"""
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.utils.decorators import method_decorator
from django.views.generic.base import View
from django.conf import settings

from edxmako.shortcuts import render_to_response
from verify_student.models import SoftwareSecurePhotoVerification


class SoftwareSecureFakeView(View):
    """
    Fake SoftwareSecure view for testing different photo verification statuses
    and email functionality.
    """

    @method_decorator(login_required)
    def get(self, request):
        """Render a fake Software Secure page.it will pick the most recent attempt
         for a given user and pass to the html page.
        """

        context_dict = self.response_post_params(request.user)

        return render_to_response("verify_student/test/fake_softwaresecure_response.html", context_dict)

    @classmethod
    def response_post_params(cls, user):
        """
        Calculate the POST params we want to send back to the client.
        """
        access_key = settings.VERIFY_STUDENT["SOFTWARE_SECURE"]["API_ACCESS_KEY"]

        context = {
            'receipt_id': None,
            'authorization_code': 'SIS {}:0000'.format(access_key),
            'results_callback': reverse('verify_student_results_callback')
        }

        try:
            most_recent = SoftwareSecurePhotoVerification.original_verification(user)
            context["receipt_id"] = most_recent.receipt_id
        except:  # pylint: disable=bare-except
            pass

        return context
