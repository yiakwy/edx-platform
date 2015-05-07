"""
Django sudo page to get sudo access.
"""

from bok_choy.page_object import PageObject


class SudoPage(PageObject):
    """
    Sudo page to get sudo access
    """
    SUDO_FORM = 'form.sudo-form'

    def __init__(self, browser, redirect_page):
        super(SudoPage, self).__init__(browser)
        self.redirect_page = redirect_page

    def is_browser_on_page(self):
        return self.q(css=self.SUDO_FORM).present

    @property
    def url(self):
        """
        Construct a URL to the page which needs sudo access.
        """
        return self.redirect_page.url

    @property
    def sudo_password_input(self):
        """
        Returns sudo password input box.
        """
        return self.q(css='{} input[id=id_password]'.format(self.SUDO_FORM))

    @property
    def submit_button(self):
        """
        Returns submit button.
        """
        return self.q(css='{} input[type=submit]'.format(self.SUDO_FORM))

    def submit_sudo_password_and_get_access(self, password):
        """
        Fill password in input field and click submit.
        """
        input_box = self.sudo_password_input.first.results[0]
        input_box.send_keys(password)
        self.click_submit()
        self.redirect_page.wait_for_page()

    def click_submit(self):
        """
        Click on submit button.
        """
        return self.submit_button.click()
