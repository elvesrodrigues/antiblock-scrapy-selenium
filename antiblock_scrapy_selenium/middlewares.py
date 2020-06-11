from importlib import import_module
from typing import List

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.http import HtmlResponse
from selenium.webdriver.support.ui import WebDriverWait

from antiblock_scrapy_selenium.http import SeleniumRequest
from antiblock_selenium import Firefox, Chrome

class SeleniumMiddleware:
    """Scrapy middleware handling the requests using selenium"""

    def __init__(self, driver_name: str, 
                    driver_executable_path: str,
                    browser_executable_path: str,
                    driver_arguments: List,
                    allow_reuse_ip_after: int,
                    change_ip_after: int,
                    user_agents: List,
                    change_user_agent_after: int,
                    time_between_calls: float,
                    random_delay: bool,
                    persist_cookies_when_close: bool,
                    reload_cookies_when_start: bool,
                    load_cookies: List,
                    location_of_cookies: str,
                    cookie_domain: str):
                    
        """Initialize the selenium webdriver
        
        Keywords arguments:
            driver_name -- The selenium ``WebDriver`` to use
            driver_executable_path -- The path of the executable binary of the driver
            driver_arguments -- A list of arguments to initialize the driver
            browser_executable_path -- The path of the executable binary of the browser
        """
        
        driver_kwargs = dict()

        if driver_name == 'firefox':
            driver_klass = Firefox

            driver_kwargs['user_agents'] = user_agents
            driver_kwargs['change_user_agent_after'] = change_user_agent_after,

        else:
            driver_klass = Chrome
            if change_user_agent_after > 0:
                raise NotConfigured('User-agent rotation is not supported for Chrome')

        if (len(load_cookies) > 0 or reload_cookies_when_start) and not cookie_domain:
            raise NotConfigured('Cookies domain must be specified')
        
        driver_options_module = import_module(f'selenium.webdriver.{driver_name}.options')
        driver_options_klass = getattr(driver_options_module, 'Options')

        driver_options = driver_options_klass()

        if browser_executable_path:
            driver_options.binary_location = browser_executable_path

        for argument in driver_arguments:
            driver_options.add_argument(argument)

        driver_kwargs['executable_path'] = driver_executable_path
        driver_kwargs['options'] = driver_options
        driver_kwargs['allow_reuse_ip_after'] = allow_reuse_ip_after
        driver_kwargs['change_ip_after'] = change_ip_after
        driver_kwargs['time_between_calls'] = time_between_calls
        driver_kwargs['random_delay'] = random_delay
        driver_kwargs['persist_cookies_when_close'] = persist_cookies_when_close
        driver_kwargs['reload_cookies_when_start'] = reload_cookies_when_start
        driver_kwargs['location_of_cookies'] = location_of_cookies
        driver_kwargs['cookie_domain'] = cookie_domain  

        self.driver = driver_klass(**driver_kwargs)

        if len(load_cookies):
            self.driver.load_cookies(load_cookies, cookie_domain)

    @classmethod
    def from_crawler(cls, crawler):
        """Initialize the middleware with the crawler settings"""
        
        driver_name = crawler.settings.get('SELENIUM_DRIVER_NAME')

        if driver_name:
            driver_name = driver_name.lower()

            if driver_name not in ['firefox', 'chrome']:
                raise NotConfigured('SELENIUM_DRIVER_NAME must be firefox or chrome')

        else:
            raise NotConfigured('SELENIUM_DRIVER_NAME must be set')

        driver_executable_path = crawler.settings.get('SELENIUM_DRIVER_EXECUTABLE_PATH', None)
        browser_executable_path = crawler.settings.get('SELENIUM_BROWSER_EXECUTABLE_PATH', None)
        driver_arguments = crawler.settings.get('SELENIUM_DRIVER_ARGUMENTS', [])

        allow_reuse_ip_after = crawler.settings.get('SELENIUM_DRIVER_ALLOW_REUSE_IP_AFTER', 10)
        change_ip_after = crawler.settings.get('SELENIUM_DRIVER_CHANGE_IP_AFTER', 42) 
        
        user_agents = crawler.settings.get('SELENIUM_DRIVER_USER_AGENTS', [])
        change_user_agent_after = crawler.settings.get('SELENIUM_DRIVER_USER_AGENTS', 0)
        
        time_between_calls = crawler.settings.get('SELENIUM_DRIVER_TIME_BETWEEN_CALLS', 0.25)
        random_delay = crawler.settings.get('SELENIUM_DRIVER_RANDOM_DELAY', True)
        
        persist_cookies_when_close = crawler.settings.get('SELENIUM_DRIVER_PERSIST_COOKIES_WHEN_CLOSE', False) 
        location_of_cookies = crawler.settings.get('SELENIUM_DRIVER_LOCATION_OF_COOKIES', 'cookies.pkl')
        reload_cookies_when_start = crawler.settings.get('SELENIUM_DRIVER_RELOAD_COOKIES_WHEN_START', False)
        load_cookies = crawler.settings.get('SELENIUM_DRIVER_LOAD_COOKIES', [])
        cookie_domain = crawler.settings.get('SELENIUM_DRIVER_COOKIE_DOMAIN', '')

        if not driver_executable_path:
            raise NotConfigured('SELENIUM_DRIVER_EXECUTABLE_PATH must be set')

        middleware = cls(
            driver_name = driver_name,
            driver_executable_path = driver_executable_path,
            browser_executable_path = browser_executable_path,
            driver_arguments = driver_arguments,
            allow_reuse_ip_after = allow_reuse_ip_after,
            change_ip_after = change_ip_after,
            user_agents = user_agents,
            change_user_agent_after = change_user_agent_after,
            time_between_calls = time_between_calls,
            random_delay = random_delay,
            persist_cookies_when_close = persist_cookies_when_close,
            reload_cookies_when_start = reload_cookies_when_start,
            load_cookies = load_cookies,
            location_of_cookies = location_of_cookies,
            cookie_domain = cookie_domain
        )

        crawler.signals.connect(middleware.spider_closed, signals.spider_closed)
        
        return middleware

    def process_request(self, request, spider):
        """Process a request using the selenium driver if applicable"""
        if not isinstance(request, SeleniumRequest):
            return None

        self.driver.get(request.url)

        for cookie_name, cookie_value in request.cookies.items():
            self.driver.add_cookie(
                {
                    'name': cookie_name,
                    'value': cookie_value
                }
            )

        if request.wait_until:
            WebDriverWait(self.driver, request.wait_time).until(
                request.wait_until
            )

        if request.screenshot:
            request.meta['screenshot'] = self.driver.get_screenshot_as_png()

        if request.script:
            self.driver.execute_script(request.script)

        body = str.encode(self.driver.page_source)

        # Expose the driver via the "meta" attribute
        request.meta.update({'driver': self.driver})

        return HtmlResponse(
            self.driver.current_url,
            body=body,
            encoding='utf-8',
            request=request
        )

    def spider_closed(self):
        """Shutdown the driver when spider is closed"""
        self.driver.quit()