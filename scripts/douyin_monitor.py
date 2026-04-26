# -*- coding: utf-8 -*-
"""
抖音爆款监控 Skill
封装为 run() 函数，从 config 读取配置
"""

import time
import json
import re
import os
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from playwright.sync_api import sync_playwright, Browser, Page

# 动态导入兼容处理
try:
    from .feishu_base import FeishuBaseClient
except ImportError:
    from feishu_base import FeishuBaseClient

# ==================== 插件元信息 ====================
SKILL_NAME = "抖音爆款监控"
SKILL_DESCRIPTION = "监控抖音关键词搜索结果，获取爆款视频数据并上传到飞书表格"


class DedupManager:
    """去重管理器"""

    def __init__(self, dedup_file: str = "dedup_records.json", hours: int = 24):
        self.dedup_file = dedup_file
        self.hours = hours
        self.records = self._load_records()

    def _load_records(self) -> Dict:
        """加载去重记录"""
        if os.path.exists(self.dedup_file):
            try:
                with open(self.dedup_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _save_records(self):
        """保存去重记录"""
        with open(self.dedup_file, "w", encoding="utf-8") as f:
            json.dump(self.records, f, ensure_ascii=False, indent=2)

    def is_duplicate(self, title: str) -> bool:
        """检查是否重复"""
        if title in self.records:
            record_time = datetime.fromisoformat(self.records[title])
            if (datetime.now() - record_time).total_seconds() < self.hours * 3600:
                return True
        return False

    def add_record(self, title: str):
        """添加记录"""
        self.records[title] = datetime.now().isoformat()
        self._save_records()


class DouyinMonitor:
    """抖音监控主类"""

    TARGET_HOST_KEYWORDS = (
        "buyin.jinritemai.com",
        "buyin.jinritemai.cn",
    )
    LOGGED_IN_TITLE_KEYWORDS = (
        "达人首页",
        "巨量百应",
        "百应",
    )

    def __init__(self, config: Dict, common_config: Dict):
        self.webhook = config.get("webhook", "")
        self.category_list = config.get("category_list", [])
        self.scroll_times = config.get("scroll_times", 20)
        self.max_cards_per_category = config.get("max_cards_per_category", 120)
        self.target_url = config.get("target_url", "")
        self.at_users = config.get("at_users", [])

        # 四层词包配置（兼容旧配置）
        keywords_config = config.get("keywords", {})
        self.primary_keywords = keywords_config.get("primary", [])
        self.expand_keywords = keywords_config.get("expand", [])
        self.explore_keywords = keywords_config.get("explore", [])
        self.exclude_keywords = keywords_config.get("exclude", [])
        
        # 向后兼容：如果没有新词包配置，使用旧配置
        if not self.primary_keywords:
            old_keywords = config.get("target_keywords", [])
            self.primary_keywords = old_keywords

        # 公共配置
        self.chrome_user_data_dir = common_config.get("chrome_user_data_dir", "")
        self.chrome_user_data_dir_independent = common_config.get("chrome_user_data_dir_independent", "")
        self.use_independent_profile = common_config.get("use_independent_profile", True)
        self.use_cdp_connect = common_config.get("use_cdp_connect", False)
        self.chrome_port = common_config.get("chrome_remote_debugging_port", 9222)
        self.wait_for_manual_login = common_config.get("wait_for_manual_login", True)
        self.login_wait_time = common_config.get("login_wait_time", 60)
        self.login_mode = common_config.get("login_mode", "manual")
        self.close_browser_on_exit = common_config.get("close_browser_on_exit", False)

        self.dedup_manager = DedupManager(
            config.get("dedup_log_file", "dedup_records.json"),
            config.get("dedup_hours", 24)
        )
        self.link_debug_file = config.get("link_debug_file", "link_debug_samples.json")
        self.results = []
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright = None

    def init_browser(self) -> bool:
        """初始化浏览器"""
        try:
            print(f"[{self._get_timestamp()}] 正在启动 Chrome 浏览器...")
            self.playwright = sync_playwright().start()

            if self.use_cdp_connect:
                print(f"[{self._get_timestamp()}] 使用 CDP 连接模式")
                try:
                    self.browser = self.playwright.chromium.connect_over_cdp(
                        f"http://localhost:{self.chrome_port}"
                    )
                    contexts = self.browser.contexts
                    if contexts:
                        pages = contexts[0].pages
                        self.page = self._select_best_page(pages) if pages else contexts[0].new_page()
                    else:
                        context = self.browser.new_context()
                        self.page = context.new_page()
                    print(f"[{self._get_timestamp()}] [OK] CDP 连接成功！")
                    return True
                except Exception as e:
                    print(f"[{self._get_timestamp()}] [ERR] CDP 连接失败: {e}")
                    return False

            user_data_dir = self.chrome_user_data_dir_independent if self.use_independent_profile else self.chrome_user_data_dir
            profile_type = "独立目录" if self.use_independent_profile else "本地 Chrome 目录"
            print(f"[{self._get_timestamp()}] 使用模式: {profile_type}")

            self.browser = self.playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check"
                ]
            )

            if self.browser.pages:
                self.page = self._select_best_page(self.browser.pages)
            else:
                self.page = self.browser.new_page()

            print(f"[{self._get_timestamp()}] [OK] 浏览器启动成功")
            return True

        except Exception as e:
            print(f"[{self._get_timestamp()}] [ERR] 浏览器启动失败: {e}")
            return False

    def check_login_status(self) -> bool:
        """检查登录状态"""
        try:
            print(f"[{self._get_timestamp()}] 检查登录状态...")
            
            time.sleep(3)
            
            current_url = self.page.url
            print(f"[{self._get_timestamp()}] [INFO] 当前URL: {current_url}")

            if not self._is_expected_target_url(current_url):
                print(f"[{self._get_timestamp()}] [INFO] 当前不在巨量百应/达人页域名下，视为未登录目标页面")
                return False
            
            if "login" in current_url.lower() or "auth" in current_url.lower():
                print(f"[{self._get_timestamp()}] [INFO] URL包含登录关键字，未登录")
                return False
            
            page_title = self.page.title()
            print(f"[{self._get_timestamp()}] [INFO] 页面标题: {page_title}")
            
            if "登录" in page_title or "Login" in page_title or "扫码" in page_title:
                print(f"[{self._get_timestamp()}] [INFO] 页面标题显示登录页")
                return False

            if any(keyword in page_title for keyword in self.LOGGED_IN_TITLE_KEYWORDS):
                print(f"[{self._get_timestamp()}] [OK] 检测到已登录业务页标题")
                return True
            
            page_content = self.page.content()
            login_indicators = ['扫码登录', '请扫码', '二维码登录', '扫码']
            
            for indicator in login_indicators:
                if indicator in page_content:
                    print(f"[{self._get_timestamp()}] [INFO] 页面包含登录元素: {indicator}")
                    return False
            
            logged_in_indicators = ['avatar', 'nickname', 'user-info', 'profile']
            
            for indicator in logged_in_indicators:
                try:
                    elem = self.page.query_selector(f"[class*='{indicator}']")
                    if elem:
                        print(f"[{self._get_timestamp()}] [OK] 检测到已登录元素: {indicator}")
                        return True
                except:
                    continue
            
            cookies = self.page.context.cookies()
            if cookies:
                print(f"[{self._get_timestamp()}] [INFO] 已保存 {len(cookies)} 个cookies")
            
            print(f"[{self._get_timestamp()}] [OK] 未检测到登录标志，认为已登录")
            return True
            
        except Exception as e:
            print(f"[{self._get_timestamp()}] [WARN] 登录状态检测失败: {e}")
            return False

    def navigate_to_target(self) -> bool:
        """导航到目标页面"""
        try:
            candidate_page = self._find_logged_in_page()
            if candidate_page:
                self.page = candidate_page
                print(f"[{self._get_timestamp()}] [OK] 已切换到更合适的标签页")

            current_url = self.page.url
            print(f"[{self._get_timestamp()}] 当前页面URL: {current_url}")
            
            if self._is_expected_target_url(current_url):
                print(f"[{self._get_timestamp()}] [OK] 已在巨量百应页面，跳过导航")
                if self.check_login_status():
                    print(f"[{self._get_timestamp()}] [OK] 已登录，继续执行")
                    return True
                else:
                    print(f"[{self._get_timestamp()}] [WARN] 页面已打开但未登录")
                    if not self.wait_for_manual_login:
                        print(f"[{self._get_timestamp()}] [INFO] 已禁用登录等待，直接继续执行...")
                        return True
                    return False
            
            print(f"[{self._get_timestamp()}] 正在打开目标页面...")
            if not self.navigate_with_fallback(self.page, self.target_url):
                return False
            print(f"[{self._get_timestamp()}] [OK] 页面加载完成")
            time.sleep(2)
            
            if self.wait_for_manual_login:
                if not self.check_login_status():
                    print(f"[{self._get_timestamp()}] [INFO] 等待用户登录...")
                    print(f"[{self._get_timestamp()}] [INFO] 请在浏览器中完成登录，登录完成后程序将继续")
                    
                    max_wait_time = 120
                    waited = 0
                    while waited < max_wait_time:
                        time.sleep(5)
                        waited += 5
                        if self.check_login_status():
                            print(f"[{self._get_timestamp()}] [OK] 登录成功！")
                            time.sleep(3)
                            return True
                        print(f"[{self._get_timestamp()}] [INFO] 等待登录中... ({waited}/{max_wait_time}秒)")
                    
                    print(f"[{self._get_timestamp()}] [WARN] 登录等待超时，继续尝试...")
            else:
                print(f"[{self._get_timestamp()}] [INFO] 已禁用登录等待，直接继续执行...")
            
            return True
        except Exception as e:
            print(f"[{self._get_timestamp()}] [ERR] 页面加载失败: {e}")
            return False

    def navigate_with_fallback(self, page, url: str, timeout: int = 30000) -> bool:
        try:
            page.goto(url, wait_until="networkidle", timeout=timeout)
            return True
        except Exception as e:
            print(f"[{self._get_timestamp()}] [WARN] networkidle 加载超时，尝试降级: {e}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                return True
            except Exception as retry_error:
                print(f"[{self._get_timestamp()}] [ERR] 页面加载失败: {retry_error}")
                return False

    @classmethod
    def _is_expected_target_url(cls, url: str) -> bool:
        if not url:
            return False
        return any(host in url for host in cls.TARGET_HOST_KEYWORDS)

    @classmethod
    def _score_page(cls, page) -> int:
        score = 0
        url = getattr(page, "url", "") or ""

        try:
            title = page.title() or ""
        except Exception:
            title = ""

        if cls._is_expected_target_url(url):
            score += 10
        if any(keyword in title for keyword in cls.LOGGED_IN_TITLE_KEYWORDS):
            score += 5
        if "dashboard" in url:
            score += 3
        if "login" in url.lower():
            score -= 10
        return score

    @classmethod
    def _select_best_page(cls, pages):
        if not pages:
            return None
        return max(pages, key=cls._score_page)

    def _find_logged_in_page(self):
        if not self.browser:
            return None

        contexts = getattr(self.browser, "contexts", [])
        all_pages = []
        for context in contexts:
            all_pages.extend(getattr(context, "pages", []))

        best_page = self._select_best_page(all_pages)
        if best_page and self._score_page(best_page) > 0:
            return best_page
        return None

    def get_card_processing_limit(self, total_cards: int) -> int:
        if not self.max_cards_per_category or self.max_cards_per_category <= 0:
            return total_cards
        return min(total_cards, self.max_cards_per_category)

    def navigate_to_explosive_videos(self) -> bool:
        """导航到爆款视频页面"""
        try:
            print(f"[{self._get_timestamp()}] 正在寻找'创作'菜单...")
            for selector in ["text=创作", "//span[contains(text(), '创作')]"]:
                try:
                    elem = self.page.wait_for_selector(selector, timeout=5000)
                    if elem:
                        elem.hover()
                        print(f"[{self._get_timestamp()}] [OK] 已悬浮'创作'菜单")
                        break
                except:
                    continue

            time.sleep(1)
            for selector in ["text=爆款视频", "//span[contains(text(), '爆款视频')]"]:
                try:
                    elem = self.page.wait_for_selector(selector, timeout=5000)
                    if elem:
                        elem.click()
                        print(f"[{self._get_timestamp()}] [OK] 已点击'爆款视频'")
                        break
                except:
                    continue

            time.sleep(3)
            self.page.mouse.move(0, 0)
            time.sleep(0.5)

            print(f"[{self._get_timestamp()}] 正在点击作者等级下的'不限'...")
            try:
                unlimited_elements = self.page.query_selector_all("text=不限")
                if len(unlimited_elements) >= 2:
                    unlimited_elements[1].click()
                    print(f"[{self._get_timestamp()}] [OK] 已点击作者等级下的'不限'")
                elif len(unlimited_elements) >= 1:
                    unlimited_elements[0].click()
                    print(f"[{self._get_timestamp()}] [OK] 已点击'不限'")
            except Exception as e:
                print(f"[{self._get_timestamp()}] [WARN] 点击作者等级'不限'失败: {e}")
            
            time.sleep(1)
            
            print(f"[{self._get_timestamp()}] 正在点击视频时长下的'不限'...")
            try:
                unlimited_elements = self.page.query_selector_all("text=不限")
                if len(unlimited_elements) >= 1:
                    unlimited_elements[0].click()
                    print(f"[{self._get_timestamp()}] [OK] 已点击视频时长下的'不限'")
            except Exception as e:
                print(f"[{self._get_timestamp()}] [WARN] 点击视频时长'不限'失败: {e}")
            
            time.sleep(2)
            return True
        except Exception as e:
            print(f"[{self._get_timestamp()}] [ERR] 导航失败: {e}")
            return False

    def click_category(self, category: str) -> bool:
        """点击指定类目"""
        try:
            print(f"[{self._get_timestamp()}] 正在进入类目：{category}...")
            selectors = [
                f"text={category}",
                f"//span[contains(text(), '{category}')]",
            ]
            for selector in selectors:
                try:
                    self.page.click(selector, timeout=5000)
                    print(f"[{self._get_timestamp()}] [OK] 成功点击类目：{category}")
                    time.sleep(5)
                    return True
                except:
                    continue
            return False
        except Exception as e:
            return False

    def scroll_and_load_data(self) -> int:
        """滚动页面加载数据"""
        try:
            print(f"[{self._get_timestamp()}] 开始滚动加载数据...")
            for i in range(self.scroll_times):
                self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                print(f"[{self._get_timestamp()}] 滚动进度: {i + 1}/{self.scroll_times}")
                time.sleep(1.5)
            print(f"[{self._get_timestamp()}] [OK] 滚动完成")
            return 0
        except Exception as e:
            return 0

    def extract_video_link(self, card, video_name: str) -> str:
        """提取视频链接"""
        card_html = self.extract_card_html(card)

        try:
            all_elems = card.query_selector_all("*")
            # 限制检查的元素数量，避免性能问题
            for elem in all_elems[:20]:
                try:
                    # 检查元素是否仍然有效
                    if not elem:
                        continue
                    for attr in ["data-video-id", "data-id", "data-url", "data-href",
                                 "data-link", "data-video-url", "data-aweme-id",
                                 "data-item-id", "data-video", "href"]:
                        try:
                            value = elem.get_attribute(attr)
                            if value:
                                if re.match(r'^\d{19}$', value):
                                    return f"https://www.douyin.com/video/{value}"
                                elif value.startswith("http"):
                                    return value
                                elif value.startswith("/video/") or value.startswith("/v/"):
                                    return f"https://www.douyin.com{value}"
                        except Exception:
                            # 元素可能已失效，继续下一个
                            continue
                except Exception:
                    # 跳过无效元素
                    continue
        except Exception as e:
            print(f"[{self._get_timestamp()}] [WARN] 提取视频链接时出错: {e}")

        # 从 HTML 中提取视频ID
        if card_html:
            try:
                html_url = self.extract_url_from_html(card_html, prefer="video")
                if html_url != "暂无链接":
                    return html_url
            except Exception:
                pass

        # 尝试从链接元素获取
        try:
            link_elem = card.query_selector("a")
            if link_elem:
                href = link_elem.get_attribute("href")
                if href and "video" in href:
                    return href if href.startswith("http") else f"https://www.douyin.com{href}"
        except Exception:
            pass

        return "暂无链接"

    def extract_product_link(self, card) -> str:
        """提取商品链接，作为视频链接不可用时的回退"""
        card_html = self.extract_card_html(card)

        attr_names = [
            "data-product-id",
            "data-item-id",
            "data-goods-id",
            "data-id",
            "data-url",
            "href",
        ]

        try:
            all_elems = card.query_selector_all("*")
            for elem in all_elems[:20]:
                for attr in attr_names:
                    try:
                        value = elem.get_attribute(attr)
                        if not value:
                            continue
                        if value.startswith("http") and "video" not in value:
                            return value
                        if re.match(r"^\d{6,}$", value):
                            return f"https://buyin.jinritemai.com/dashboard/goodsDetail?productId={value}"
                    except Exception:
                        continue
        except Exception:
            pass

        if card_html:
            try:
                html_url = self.extract_url_from_html(card_html, prefer="product")
                if html_url != "暂无链接":
                    return html_url
            except Exception:
                pass

        try:
            link_elem = card.query_selector("a")
            if link_elem:
                href = link_elem.get_attribute("href")
                if href and "video" not in href:
                    return href if href.startswith("http") else f"https://buyin.jinritemai.com{href}"
        except Exception:
            pass

        return "暂无链接"

    def extract_card_html(self, card) -> str:
        try:
            html = card.get_attribute("outerHTML")
            if html:
                return html
        except Exception:
            pass

        try:
            html = card.evaluate("(el) => el.outerHTML || ''")
            if html:
                return html
        except Exception:
            pass

        return ""

    def extract_candidate_strings(self, card) -> List[str]:
        candidates = []

        try:
            payload = card.evaluate(
                """(el) => {
                    const values = [];
                    const push = (v) => {
                        if (typeof v === 'string' && v.trim()) values.push(v.trim());
                    };

                    const nodes = [el, ...el.querySelectorAll('*')].slice(0, 30);
                    for (const node of nodes) {
                        if (node.href) push(node.href);
                        for (const attr of node.getAttributeNames ? node.getAttributeNames() : []) {
                            push(node.getAttribute(attr));
                        }
                        if (node.dataset) {
                            for (const value of Object.values(node.dataset)) push(value);
                        }
                    }
                    return values;
                }"""
            )
            if isinstance(payload, list):
                candidates.extend(payload)
        except Exception:
            pass

        return candidates

    def extract_url_from_html(self, html: str, prefer: str = "video") -> str:
        if not html:
            return "暂无链接"

        def first_match(patterns):
            for pattern in patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    return match.group(1)
            return None

        video_id = first_match([
            r'data-aweme-id=["\'](\d{19})["\']',
            r'data-video-id=["\'](\d{19})["\']',
            r'"aweme_id"\s*:\s*"(\d{19})"',
            r'"videoId"\s*:\s*"(\d{19})"',
            r'\b(\d{19})\b',
        ])
        product_id = first_match([
            r'data-product-id=["\'](\d{6,})["\']',
            r'data-goods-id=["\'](\d{6,})["\']',
            r'"productId"\s*:\s*"?(\\d{6,})"?',
            r'"goodsId"\s*:\s*"?(\\d{6,})"?',
            r'"itemId"\s*:\s*"?(\\d{6,})"?',
        ])
        direct_url = first_match([
            r'(https?://[^"\']+)',
            r'(//buyin\.jinritemai\.com[^"\']+)',
            r'(/dashboard/[^"\']+)',
        ])

        def normalize_url(url: str) -> str:
            if not url:
                return ""
            if url.startswith("//"):
                return f"https:{url}"
            if url.startswith("/"):
                return f"https://buyin.jinritemai.com{url}"
            return url

        def is_allowed_view_url(url: str) -> bool:
            if not url:
                return False
            lowered = url.lower()
            blocked_domains = [
                "douyinpic.com",
                "tos-cn-p-0015",
                "tplv-noop.image",
            ]
            if any(domain in lowered for domain in blocked_domains):
                return False
            allowed_domains = [
                "douyin.com/video/",
                "buyin.jinritemai.com",
                "buyin.jinritemai.cn",
            ]
            return any(domain in lowered for domain in allowed_domains)

        if prefer == "video":
            if video_id:
                return f"https://www.douyin.com/video/{video_id}"
            normalized_direct_url = normalize_url(direct_url)
            if normalized_direct_url and "video" in normalized_direct_url and is_allowed_view_url(normalized_direct_url):
                return normalized_direct_url

        if product_id:
            return f"https://buyin.jinritemai.com/dashboard/goodsDetail?productId={product_id}"
        if direct_url:
            normalized_direct_url = normalize_url(direct_url)
            if is_allowed_view_url(normalized_direct_url):
                return normalized_direct_url
        if prefer != "video" and video_id:
            return f"https://www.douyin.com/video/{video_id}"
        return "暂无链接"

    def extract_url_from_candidates(self, candidates: List[str], prefer: str = "video") -> str:
        if not candidates:
            return "暂无链接"

        joined = "\n".join(candidates)
        return self.extract_url_from_html(joined, prefer=prefer)

    @staticmethod
    def is_actionable_view_url(url: str) -> bool:
        if not url or url == "暂无链接":
            return False

        lowered = url.lower()
        blocked_domains = (
            "douyinpic.com",
            "tos-cn-p-0015",
            "tplv-noop.image",
        )
        if any(domain in lowered for domain in blocked_domains):
            return False

        allowed_domains = (
            "https://www.douyin.com/video/",
            "https://buyin.jinritemai.com",
            "https://buyin.jinritemai.cn",
        )
        return any(lowered.startswith(domain) for domain in allowed_domains)

    @classmethod
    def normalize_view_url(cls, url: str) -> str:
        if not cls.is_actionable_view_url(url):
            return "暂无链接"

        try:
            parsed = urlparse(url)
            if "buyin.jinritemai." not in parsed.netloc:
                return url

            query = parse_qs(parsed.query, keep_blank_values=False)
            keep_keys = []

            if parsed.path.endswith("/goodsDetail"):
                keep_keys = ["productId"]
            elif parsed.path.endswith("/merch-promoting"):
                keep_keys = ["id"]

            if not keep_keys:
                return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

            compact_query = []
            for key in keep_keys:
                for value in query.get(key, []):
                    if value:
                        compact_query.append((key, value))

            compact_query_string = urlencode(compact_query)
            return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", compact_query_string, ""))
        except Exception:
            return url

    @classmethod
    def resolve_view_url(cls, video_url: str, product_url: str) -> str:
        for candidate in (product_url, video_url):
            if cls.is_actionable_view_url(candidate):
                return cls.normalize_view_url(candidate)
        return "暂无链接"

    def _capture_actionable_navigation_url(self, previous_url: str, previous_pages: List, timeout_seconds: int = 5) -> str:
        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            current_url = getattr(self.page, "url", "")
            if current_url != previous_url and self.is_actionable_view_url(current_url):
                try:
                    self.page.go_back(wait_until="domcontentloaded", timeout=10000)
                except Exception:
                    pass
                return current_url

            current_pages = list(getattr(self.page.context, "pages", []))
            for candidate_page in current_pages:
                if candidate_page in previous_pages:
                    continue
                candidate_url = getattr(candidate_page, "url", "")
                if self.is_actionable_view_url(candidate_url):
                    try:
                        candidate_page.close()
                    except Exception:
                        pass
                    return candidate_url

            time.sleep(0.2)

        return "暂无链接"

    def extract_product_link_by_click(self, card_index: int) -> str:
        if not self.page or card_index < 0:
            return "暂无链接"

        try:
            cards = self.page.query_selector_all("[class*='videoCard_item']")
        except Exception:
            return "暂无链接"

        if card_index >= len(cards):
            return "暂无链接"

        card = cards[card_index]
        selectors = [
            "[class*='singleProductsName']",
            "[class*='singleProducts']",
            "[class*='product']",
            "[class*='goods']",
        ]

        for selector in selectors:
            try:
                elem = card.query_selector(selector)
                if not elem:
                    continue

                previous_url = getattr(self.page, "url", "")
                previous_pages = list(getattr(self.page.context, "pages", []))

                try:
                    elem.scroll_into_view_if_needed()
                except Exception:
                    pass

                elem.click(timeout=3000)
                clicked_url = self._capture_actionable_navigation_url(previous_url, previous_pages)
                if clicked_url != "暂无链接":
                    return clicked_url
            except Exception:
                continue

        return "暂无链接"

    def save_link_debug_sample(self, product: Dict, matched_keyword: str):
        sample = {
            "timestamp": datetime.now().isoformat(),
            "title": product.get("title", ""),
            "video_name": product.get("video_name", ""),
            "matched_keyword": matched_keyword,
            "video_link": product.get("video_link", "暂无链接"),
            "product_link": product.get("product_link", "暂无链接"),
            "html_snippet": product.get("raw_html", "")[:4000],
        }

        existing = []
        if os.path.exists(self.link_debug_file):
            try:
                with open(self.link_debug_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        if len(existing) >= 5:
            return

        existing.append(sample)
        with open(self.link_debug_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    def extract_author_from_card(self, card) -> str:
        """提取作者名字"""
        author_selectors = [
            "[class*='author']",
            "[class*='nickname']",
            "[class*='userName']",
            "[class*='name']",
            "[class*='user']",
        ]

        for selector in author_selectors:
            try:
                elem = card.query_selector(selector)
                if elem:
                    author_text = elem.text_content().strip()
                    if "LV" in author_text or len(author_text) < 50:
                        author_name = re.sub(r'\s*[\+@]*\s*LV\d+', '', author_text).strip()
                        author_name = re.sub(r'\s*[\+@]+$', '', author_name).strip()
                        if author_name and len(author_name) < 30:
                            return author_name
            except:
                continue

        return "暂无"

    def extract_duration_from_card(self, card) -> str:
        """提取视频时长"""
        duration_selectors = [
            "[class*='endTime']",
            "[class*='duration']",
            "[class*='time']:last-child",
        ]

        for selector in duration_selectors:
            try:
                elem = card.query_selector(selector)
                if elem:
                    duration_text = elem.text_content().strip()
                    if re.match(r'^\d+秒$', duration_text) or re.match(r'^\d+分\d+秒$', duration_text):
                        return duration_text
            except:
                continue

        return "暂无"

    def parse_card_data(self, card_text: str) -> Dict:
        """解析卡片数据"""
        data = {
            "play_count": "暂无",
            "likes": "暂无",
            "author": "暂无",
            "duration": "暂无",
            "publish_time": "暂无",
            "sales": "暂无",
            "orders": "暂无",
        }

        time_match = re.search(r'(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})', card_text)
        if time_match:
            data["publish_time"] = time_match.group(1)

        author_match = re.search(r'([\u4e00-\u9fa5a-zA-Z]+)\s*[@\+]?\s*LV\d+', card_text)
        if author_match:
            data["author"] = author_match.group(1)

        sales_match = re.search(r'已选类目销售额\s*(\d+\.?\d*[- ]?\d*\.?\d*万?|\d+\.?\d*万)', card_text)
        if sales_match:
            data["sales"] = sales_match.group(1)

        orders_match = re.search(r'已选类目成交单量\s*(\d+[- ]\d+|\d+\.?\d*万[- ]\d*\.?\d*万|\d+\.?\d*万)', card_text)
        if orders_match:
            data["orders"] = orders_match.group(1)

        play_match = re.search(r'总播放量\s*(\d+\.?\d*[\+↑\s]*\d*\.?\d*[万+]?)', card_text)
        if play_match:
            play_value = play_match.group(1).strip()
            play_value = re.sub(r'\s+', '', play_value)
            play_clean = re.split(r'[↑\s]+', play_value)[0]
            data["play_count"] = play_clean
        else:
            play_alt = re.search(r'(\d+\.?\d*万\+)', card_text)
            if play_alt:
                data["play_count"] = play_alt.group(1)

        likes_match = re.search(r'总点赞量\s*(\d+\.?\d*[万+]?)', card_text)
        if likes_match:
            data["likes"] = likes_match.group(1)

        return data

    def extract_product_data(self, category: str) -> List[Dict]:
        """提取当前页面的商品数据"""
        products = []

        try:
            cards = self.page.query_selector_all("[class*='videoCard_item']")
            print(f"[{self._get_timestamp()}] 找到 {len(cards)} 个视频卡片")
            
            max_cards = self.get_card_processing_limit(len(cards))
            print(f"[{self._get_timestamp()}] 本类将处理 {max_cards}/{len(cards)} 个卡片")

            for idx, card in enumerate(cards[:max_cards]):
                try:
                    if idx and idx % 20 == 0:
                        print(f"[{self._get_timestamp()}] 提取进度: {idx}/{max_cards}")

                    # 检查卡片是否仍然有效
                    if not card:
                        print(f"[{self._get_timestamp()}] [WARN] 卡片 {idx} 已失效，跳过")
                        continue

                    video_name_elem = card.query_selector("[class*='videoName']")
                    video_name = ""
                    if video_name_elem:
                        try:
                            video_name = video_name_elem.text_content() or ""
                            video_name = video_name.strip()
                        except Exception as e:
                            print(f"[{self._get_timestamp()}] [WARN] 卡片 {idx} video_name 提取失败: {e}")

                    product_name_elem = card.query_selector("[class*='singleProductsName']")
                    product_name = ""
                    if product_name_elem:
                        try:
                            product_name = product_name_elem.text_content() or ""
                            product_name = product_name.strip()
                        except Exception as e:
                            print(f"[{self._get_timestamp()}] [WARN] 卡片 {idx} product_name 提取失败: {e}")

                    # 如果两个名称都为空，跳过
                    if not video_name and not product_name:
                        continue

                    card_html = self.extract_card_html(card)
                    candidate_strings = self.extract_candidate_strings(card)

                    card_text = ""
                    try:
                        card_text = card.text_content() or ""
                    except Exception as e:
                        print(f"[{self._get_timestamp()}] [WARN] 卡片 {idx} 文本提取失败，跳过: {e}")
                        continue
                    
                    parsed_data = self.parse_card_data(card_text)

                    # 安全地提取作者和时长
                    try:
                        author_from_selector = self.extract_author_from_card(card)
                        if author_from_selector != "暂无":
                            parsed_data["author"] = author_from_selector
                    except Exception as e:
                        print(f"[{self._get_timestamp()}] [WARN] 卡片 {idx} 作者提取失败: {e}")

                    try:
                        duration_from_selector = self.extract_duration_from_card(card)
                        if duration_from_selector != "暂无":
                            parsed_data["duration"] = duration_from_selector
                    except Exception as e:
                        print(f"[{self._get_timestamp()}] [WARN] 卡片 {idx} 时长提取失败: {e}")

                    # 提取视频链接
                    try:
                        video_link = self.extract_video_link(card, video_name)
                        if video_link == "暂无链接":
                            video_link = self.extract_url_from_candidates(candidate_strings, prefer="video")
                    except Exception as e:
                        print(f"[{self._get_timestamp()}] [WARN] 卡片 {idx} 视频链接提取失败: {e}")
                        video_link = "暂无链接"

                    try:
                        product_link = self.extract_product_link(card)
                        if product_link == "暂无链接":
                            product_link = self.extract_url_from_candidates(candidate_strings, prefer="product")
                    except Exception as e:
                        print(f"[{self._get_timestamp()}] [WARN] 卡片 {idx} 商品链接提取失败: {e}")
                        product_link = "暂无链接"

                    title = product_name if product_name else video_name

                    if title and len(title) > 5:
                        products.append({
                            "title": title,
                            "video_name": video_name,
                            "play_count": parsed_data.get("play_count", "暂无"),
                            "link": self.resolve_view_url(video_link, product_link),
                            "video_link": video_link,
                            "product_link": product_link,
                            "category": category,
                            "likes": parsed_data.get("likes", "暂无"),
                            "author": parsed_data.get("author", "暂无"),
                            "duration": parsed_data.get("duration", "暂无"),
                            "publish_time": parsed_data.get("publish_time", "暂无"),
                            "sales": parsed_data.get("sales", "暂无"),
                            "orders": parsed_data.get("orders", "暂无"),
                            "raw_html": card_html,
                            "card_index": idx,
                        })

                except Exception as e:
                    print(f"[{self._get_timestamp()}] [WARN] 提取卡片 {idx} 数据时出错: {e}")
                    continue

            print(f"[{self._get_timestamp()}] [OK] 成功提取 {len(products)} 条有效数据")

        except Exception as e:
            print(f"[{self._get_timestamp()}] [ERR] 数据提取失败: {e}")
            import traceback
            traceback.print_exc()

        return products

    def check_keywords(self, title: str) -> Tuple[Optional[str], str]:
        """检查标题是否包含目标关键词，返回 (匹配词, 置信度)"""
        # 先检查排除词
        for keyword in self.exclude_keywords:
            if keyword in title:
                return None, "排除"
        
        # 检查主推词（高置信度）
        for keyword in self.primary_keywords:
            if keyword in title:
                return keyword, "高"
        
        # 检查探索词（中置信度）
        for keyword in self.explore_keywords:
            if keyword in title:
                return keyword, "中"
        
        # 检查扩展词（低置信度）
        for keyword in self.expand_keywords:
            if keyword in title:
                return keyword, "低"
        
        return None, "无"

    def get_feishu_token(self, app_id: str, app_secret: str) -> Optional[str]:
        """获取飞书 tenant_access_token"""
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        headers = {"Content-Type": "application/json; charset=utf-8"}
        payload = {"app_id": app_id, "app_secret": app_secret}
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            data = resp.json()
            if data.get("code") == 0:
                return data.get("tenant_access_token")
            else:
                print(f"[{self._get_timestamp()}] [ERR] 获取飞书token失败: {data.get('msg')}")
                return None
        except Exception as e:
            print(f"[{self._get_timestamp()}] [ERR] 获取飞书token异常: {e}")
            return None

    def send_feishu_alert(self, **kwargs):
        """发送飞书通知（同时支持webhook和API）"""
        import requests

        content = self.build_feishu_alert_content(**kwargs)

        if self.webhook:
            payload = {
                "msg_type": "text",
                "content": {"text": content}
            }
            try:
                response = requests.post(self.webhook, json=payload, timeout=10)
                if response.status_code == 200:
                    print(f"[{self._get_timestamp()}] [OK] Webhook通知已发送")
                else:
                    print(f"[{self._get_timestamp()}] [ERR] Webhook发送失败，HTTP状态码: {response.status_code}")
            except Exception as e:
                print(f"[{self._get_timestamp()}] [ERR] Webhook发送失败: {e}")

        feishu_config = kwargs.get('feishu_config') or {}
        app_id = feishu_config.get('app_id')
        app_secret = feishu_config.get('app_secret')
        chat_id = feishu_config.get('chat_id')

        if app_id and app_secret and chat_id and app_id != "请填入你的飞书应用ID":
            token = self.get_feishu_token(app_id, app_secret)
            if token:
                url = "https://open.feishu.cn/open-apis/im/v1/messages"
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "receive_id_type": "chat_id",
                    "receive_id": chat_id,
                    "msg_type": "text",
                    "content": json.dumps({"text": content})
                }
                try:
                    resp = requests.post(url, headers=headers, json=payload, timeout=10)
                    data = resp.json()
                    if data.get("code") == 0:
                        print(f"[{self._get_timestamp()}] [OK] Feishu API通知已发送到群")
                    else:
                        print(f"[{self._get_timestamp()}] [ERR] Feishu API发送失败: {data.get('msg')}")
                except Exception as e:
                    print(f"[{self._get_timestamp()}] [ERR] Feishu API发送异常: {e}")

    def build_feishu_alert_content(self, **kwargs) -> str:
        at_str = ""
        at_users = kwargs.get('at_users', [])
        if at_users:
            at_str = "".join([f"@{user} " for user in at_users])
        
        confidence = kwargs.get('confidence', '高')
        confidence_emoji = {"高": "🔥", "中": "⭐", "低": "📌"}.get(confidence, "📌")
        matched_keyword = kwargs.get("matched_keyword", "暂无")
        view_url = self.resolve_view_url(
            kwargs.get("video_url", "暂无链接"),
            kwargs.get("product_url", "暂无链接"),
        )

        return f"""{at_str}爆款
【爆款提醒】发现潜力选品！{confidence_emoji} 置信度: {confidence}  命中关键词: {matched_keyword}
━━━━━━━━━━━━━━━
📦 商品名称：{kwargs.get('title', '')}
🎬 视频标题：{kwargs.get('video_title', '')}
👤 作者：{kwargs.get('author', '')}
━━━━━━━━━━━━━━━
📊 播放量：{kwargs.get('play_count', '')}
❤️ 点赞量：{kwargs.get('likes', '')}
━━━━━━━━━━━━━━━
🏷️ 类目：{kwargs.get('category', '')}
💰 已选类目销售额：{kwargs.get('sales', '')}
📦 已选类目成交单量：{kwargs.get('orders', '')}
━━━━━━━━━━━━━━━
⏱️ 视频时长：{kwargs.get('duration', '')}
🕐 发布时间：{kwargs.get('publish_time', '')}
━━━━━━━━━━━━━━━
🔗 查看链接：{view_url}
"""

    def process_products(self, products: List[Dict], category: str, feishu_config: Dict = None):
        """处理商品数据"""
        for product in products:
            title = product.get("title", "")
            matched_keyword, confidence = self.check_keywords(title)

            if matched_keyword:
                print(f"[{self._get_timestamp()}] [HIT] 命中关键词: [{matched_keyword}] 置信度:{confidence} - {title}")

                if not self.dedup_manager.is_duplicate(title):
                    resolved_url = self.resolve_view_url(
                        product.get("video_link", "暂无链接"),
                        product.get("product_link", "暂无链接"),
                    )

                    if resolved_url == "暂无链接":
                        interactive_product_link = self.extract_product_link_by_click(product.get("card_index", -1))
                        if interactive_product_link != "暂无链接":
                            product["product_link"] = interactive_product_link
                            resolved_url = self.resolve_view_url(
                                product.get("video_link", "暂无链接"),
                                product.get("product_link", "暂无链接"),
                            )

                    if resolved_url == "暂无链接":
                        self.save_link_debug_sample(product, matched_keyword)
                    self.send_feishu_alert(
                        category=category,
                        title=title,
                        video_title=product.get("video_name", "暂无"),
                        play_count=product.get("play_count", "暂无"),
                        video_url=product.get("video_link", "暂无链接"),
                        product_url=product.get("product_link", "暂无链接"),
                        duration=product.get("duration", "暂无"),
                        publish_time=product.get("publish_time", "暂无"),
                        author=product.get("author", "暂无"),
                        sales=product.get("sales", "暂无"),
                        orders=product.get("orders", "暂无"),
                        likes=product.get("likes", "暂无"),
                        at_users=self.at_users,
                        feishu_config=feishu_config,
                        confidence=confidence,
                        matched_keyword=matched_keyword,
                    )
                    self.dedup_manager.add_record(title)
                    self.results.append(product)
                else:
                    print(f"[{self._get_timestamp()}] [SKIP] 已推送过，跳过")

    def run(self, feishu_config: Dict = None):
        """执行主流程"""
        print("=" * 50)
        print("抖音监控脚本")
        print("=" * 50)

        if not self.init_browser():
            return
        if not self.navigate_to_target():
            return
        if not self.navigate_to_explosive_videos():
            return

        for category in self.category_list:
            print(f"\n{'='*20} 开始处理类目: {category} {'='*20}")

            if not self.click_category(category):
                print(f"跳过类目: {category}")
                continue

            self.scroll_and_load_data()
            products = self.extract_product_data(category)

            if products:
                self.process_products(products, category, feishu_config)
            else:
                print(f"[{self._get_timestamp()}] 未抓取到数据")

            print(f"{'='*20} 类目 {category} 处理完成 {'='*20}\n")

        self.print_summary()

    def print_summary(self):
        """打印执行摘要"""
        print("\n" + "=" * 50)
        print("监控执行完成！")
        print("=" * 50)
        print(f"共发现 {len(self.results)} 个匹配商品")
        if self.results:
            print("\n匹配列表:")
            for idx, item in enumerate(self.results, 1):
                print(f"{idx}. {item.get('title', '')}")
        print("=" * 50)

    @staticmethod
    def _get_timestamp() -> str:
        return datetime.now().strftime("%H:%M:%S")

    def should_close_browser(self) -> bool:
        return bool(self.close_browser_on_exit)


def run(config: Dict, common_config: Dict):
    """运行抖音爆款监控"""
    skill_config = config.get("skills", {}).get("douyin_monitor", {})
    
    feishu_global = config.get("feishu_global", {})
    feishu_config = {
        "app_id": feishu_global.get("app_id", ""),
        "app_secret": feishu_global.get("app_secret", ""),
        "chat_id": skill_config.get("chat_id", "")
    }

    monitor = DouyinMonitor(skill_config, common_config)
    try:
        monitor.run(feishu_config)
    except KeyboardInterrupt:
        print(f"\n[{monitor._get_timestamp()}] 用户中断程序")
    except Exception as e:
        print(f"\n[{monitor._get_timestamp()}] 程序异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if monitor.browser:
            if monitor.use_cdp_connect:
                print(f"\n[{monitor._get_timestamp()}] 保持浏览器连接，请手动关闭")
            else:
                if monitor.should_close_browser():
                    print(f"\n[{monitor._get_timestamp()}] 自动关闭浏览器...")
                    monitor.browser.close()
                    if monitor.playwright:
                        monitor.playwright.stop()
                else:
                    print(f"\n[{monitor._get_timestamp()}] 保持浏览器打开，以便保留登录状态")
