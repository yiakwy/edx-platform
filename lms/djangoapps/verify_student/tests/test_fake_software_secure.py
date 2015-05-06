"""
Tests for the  fake software secure reponse.
"""

from django.conf import settings
from django.test import TestCase
from django.test.utils import override_settings
from mock import patch
import mock
from student.tests.factories import UserFactory
from verify_student.models import SoftwareSecurePhotoVerification


class SoftwareSecureFakeViewTest(TestCase):
    """Test the fake software secure reponse"""

    def setUp(self):
        super(SoftwareSecureFakeViewTest, self).setUp()
        self.user = UserFactory.create(username="test", password="test")
        self.attempt = SoftwareSecurePhotoVerification.objects.create(user=self.user)
        self.client.login(username="test", password="test")

    @patch.dict(settings.FEATURES, {'ENABLE_SOFTWARE_SECURE_FAKE': False})
    def test_get_method_without_enable_feature_flag(self):
        # Without enable the feature it will return the 404
        response = self.client.get(
            '/verify_student/software-secure-fake-response'
        )

        self.assertEqual(response.status_code, 404)

    @patch.dict(settings.FEATURES, {'ENABLE_SOFTWARE_SECURE_FAKE': True})
    def test_get_method_without_logged_in_user(self):
        # Without enable the feature it will return the 302
        self.client.logout()
        response = self.client.get(
            '/verify_student/software-secure-fake-response'
        )

        self.assertEqual(response.status_code, 302)

    @patch.dict(settings.FEATURES, {'ENABLE_SOFTWARE_SECURE_FAKE': True})
    def test_get_method(self):

        # GET request to the fake view will get the most recent attempt for
        # a logged-in user

        response = self.client.get(
            '/verify_student/software-secure-fake-response'
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('EdX-ID', response.content)
        self.assertIn('results_callback', response.content)
