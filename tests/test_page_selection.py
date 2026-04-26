import unittest

from scripts.douyin_monitor import DouyinMonitor


class FakePage:
    def __init__(self, url, title):
        self.url = url
        self._title = title

    def title(self):
        return self._title


class FakeGotoPage(FakePage):
    def __init__(self, failures=None):
        super().__init__("about:blank", "新标签页")
        self.failures = list(failures or [])
        self.calls = []

    def goto(self, url, wait_until=None, timeout=None):
        self.calls.append((url, wait_until, timeout))
        if self.failures:
            error = self.failures.pop(0)
            if error is not None:
                raise error
        self.url = url


class FakeClickableElement:
    def __init__(self, on_click=None):
        self.on_click = on_click

    def scroll_into_view_if_needed(self):
        return None

    def click(self, timeout=None):
        if self.on_click:
            self.on_click()


class FakeCard:
    def __init__(self, mapping=None):
        self.mapping = mapping or {}

    def query_selector(self, selector):
        return self.mapping.get(selector)


class FakeContext:
    def __init__(self, pages=None):
        self.pages = list(pages or [])


class FakeInteractivePage(FakePage):
    def __init__(self, url):
        super().__init__(url, "列表页")
        self.cards = []
        self.context = FakeContext([self])
        self._history = []

    def query_selector_all(self, selector):
        if selector == "[class*='videoCard_item']":
            return self.cards
        return []

    def go_back(self, wait_until=None, timeout=None):
        if self._history:
            self.url = self._history.pop()


class PageSelectionTests(unittest.TestCase):
    def test_marketing_homepage_is_not_target_url(self):
        self.assertFalse(DouyinMonitor._is_expected_target_url("https://www.douyinec.com/"))

    def test_buyin_dashboard_is_target_url(self):
        self.assertTrue(
            DouyinMonitor._is_expected_target_url("https://buyin.jinritemai.com/dashboard")
        )

    def test_select_best_page_prefers_logged_in_buyin_tab(self):
        pages = [
            FakePage("about:blank", "新标签页"),
            FakePage("https://www.douyinec.com/", "抖音电商官网"),
            FakePage("https://buyin.jinritemai.com/dashboard", "达人首页"),
        ]

        best_page = DouyinMonitor._select_best_page(pages)

        self.assertEqual(best_page.url, "https://buyin.jinritemai.com/dashboard")

    def test_browser_stays_open_by_default(self):
        monitor = DouyinMonitor({}, {})
        self.assertFalse(monitor.should_close_browser())

    def test_browser_can_be_closed_when_explicitly_enabled(self):
        monitor = DouyinMonitor({}, {"close_browser_on_exit": True})
        self.assertTrue(monitor.should_close_browser())

    def test_navigate_with_fallback_retries_after_timeout(self):
        monitor = DouyinMonitor({}, {})
        page = FakeGotoPage([Exception("Timeout 30000ms exceeded."), None])

        result = monitor.navigate_with_fallback(page, "https://buyin.jinritemai.com/dashboard")

        self.assertTrue(result)
        self.assertEqual(
            page.calls,
            [
                ("https://buyin.jinritemai.com/dashboard", "networkidle", 30000),
                ("https://buyin.jinritemai.com/dashboard", "domcontentloaded", 30000),
            ],
        )

    def test_card_processing_limit_defaults_to_120(self):
        monitor = DouyinMonitor({}, {})
        self.assertEqual(monitor.get_card_processing_limit(174), 120)

    def test_card_processing_limit_respects_smaller_config(self):
        monitor = DouyinMonitor({"max_cards_per_category": 80}, {})
        self.assertEqual(monitor.get_card_processing_limit(174), 80)

    def test_build_alert_content_shows_keyword_on_same_line(self):
        monitor = DouyinMonitor({}, {})

        content = monitor.build_feishu_alert_content(
            title="测试商品",
            video_title="测试视频",
            confidence="中",
            matched_keyword="出差",
            view_url="https://example.com/item/1",
        )

        self.assertIn("置信度: 中", content)
        self.assertIn("命中关键词: 出差", content)
        self.assertIn("置信度: 中  命中关键词: 出差", content)

    def test_resolve_view_url_prefers_product_then_video(self):
        monitor = DouyinMonitor({}, {})

        self.assertEqual(
            monitor.resolve_view_url(
                "https://www.douyin.com/video/1234567890123456789",
                "https://buyin.jinritemai.com/dashboard/goodsDetail?productId=987654321",
            ),
            "https://buyin.jinritemai.com/dashboard/goodsDetail?productId=987654321",
        )
        self.assertEqual(
            monitor.resolve_view_url(
                "暂无链接",
                "https://buyin.jinritemai.com/dashboard/goodsDetail?productId=987654321",
            ),
            "https://buyin.jinritemai.com/dashboard/goodsDetail?productId=987654321",
        )

    def test_resolve_view_url_ignores_image_cdn_and_uses_product(self):
        monitor = DouyinMonitor({}, {})
        image_url = "https://p26-sign.douyinpic.com/tos-cn-p-0015/abc~tplv-noop.image?x-signature=123"
        product_url = "https://buyin.jinritemai.com/dashboard/goodsDetail?productId=987654321"
        self.assertEqual(monitor.resolve_view_url(image_url, product_url), product_url)

    def test_resolve_view_url_strips_tracking_params_from_product_link(self):
        monitor = DouyinMonitor({}, {})
        product_url = (
            "https://buyin.jinritemai.com/dashboard/merch-picking-library/merch-promoting"
            "?id=3802802634411343934&btm_ppre=a10091.b089178.c0.d0"
            "&btm_pre=a10091.b041592.c0.d0&btm_show_id=02c30421-f75f-426e-8df5-8c39e9394594"
            "&pre_universal_page_params_id=&universal_page_params_id=ae795be5-fc81-47ee-b1d3-048a3eb5730c"
        )
        self.assertEqual(
            monitor.resolve_view_url("暂无链接", product_url),
            "https://buyin.jinritemai.com/dashboard/merch-picking-library/merch-promoting?id=3802802634411343934",
        )

    def test_extract_url_from_html_finds_video_id(self):
        monitor = DouyinMonitor({}, {})
        html = '<div data-aweme-id="1234567890123456789"></div>'
        self.assertEqual(
            monitor.extract_url_from_html(html, prefer="video"),
            "https://www.douyin.com/video/1234567890123456789",
        )

    def test_extract_url_from_html_finds_product_id(self):
        monitor = DouyinMonitor({}, {})
        html = '<div data-product-id="987654321"></div>'
        self.assertEqual(
            monitor.extract_url_from_html(html, prefer="product"),
            "https://buyin.jinritemai.com/dashboard/goodsDetail?productId=987654321",
        )

    def test_extract_url_from_html_ignores_image_cdn_links(self):
        monitor = DouyinMonitor({}, {})
        html = '<img src="https://p26-sign.douyinpic.com/tos-cn-p-0015/abc~tplv-noop.image?x-signature=123" />'
        self.assertEqual(monitor.extract_url_from_html(html, prefer="video"), "暂无链接")

    def test_extract_product_link_by_click_uses_product_strip_navigation(self):
        monitor = DouyinMonitor({}, {})
        page = FakeInteractivePage("https://buyin.jinritemai.com/dashboard")
        product_url = "https://buyin.jinritemai.com/dashboard/goodsDetail?productId=987654321"

        def navigate():
            page._history.append(page.url)
            page.url = product_url

        product_elem = FakeClickableElement(on_click=navigate)
        page.cards = [FakeCard({"[class*='singleProductsName']": product_elem})]
        monitor.page = page

        self.assertEqual(monitor.extract_product_link_by_click(0), product_url)
        self.assertEqual(page.url, "https://buyin.jinritemai.com/dashboard")


if __name__ == "__main__":
    unittest.main()
