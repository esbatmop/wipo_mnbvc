# -*- coding: utf-8 -*-
import time
import json
import os
import sys
import csv
import logging
from DrissionPage import ChromiumPage
from parsel import Selector
from functools import wraps

# -------------------- 配置部分 --------------------
class Config:
    # 文件路径配置
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    LOG_FILE = os.path.join(BASE_DIR, 'wipo_crawler.log')
    DATA_FILE = os.path.join(BASE_DIR, 'wipo_data.csv')
    IPC_LIST_FILE = os.path.join(BASE_DIR, 'wipo_ipcs_list.txt')
    
    # 爬虫参数
    DEFAULT_IPC = 'A23P20/17'
    MAX_RETRY = 3
    PAGE_LOAD_TIMEOUT = 15
    ACTION_DELAY = 1.5
    PAGE_LIMIT = 200

# -------------------- 工具函数 --------------------
def setup_logging():
    """配置日志系统"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(Config.LOG_FILE),
            logging.StreamHandler()
        ]
    )

def retry(retries=3, delay=5, exceptions=(Exception,)):
    """重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == retries:
                        raise
                    logging.warning(f"Attempt {attempt} failed: {str(e)}. Retrying in {delay}s...")
                    time.sleep(delay)
        return wrapper
    return decorator

# -------------------- 核心爬虫类 --------------------
class WIPOCrawler:
    def __init__(self):
        self.browser = ChromiumPage()
        self.current_ipc = None
        self.processed_ipcs = set()
        
        # 初始化状态
        self._load_processed_ipcs()
        
    def _load_processed_ipcs(self):
        """加载已处理的IPC列表"""
        if os.path.exists(Config.LOG_FILE):
            with open(Config.LOG_FILE, 'r') as f:
                self.processed_ipcs = set(line.strip() for line in f)

    @retry(retries=Config.MAX_RETRY, delay=5)
    def _safe_click(self, selector, description="元素"):
        """安全点击元素"""
        elem = self.browser.ele(selector, timeout=Config.PAGE_LOAD_TIMEOUT)
        if not elem:
            raise ElementNotFoundError(f"{description}未找到: {selector}")
        elem.click()
        time.sleep(Config.ACTION_DELAY)
        return True

    @retry(retries=Config.MAX_RETRY, delay=10)
    def _safe_input(self, selector, text, description="输入框"):
        """安全输入文本"""
        elem = self.browser.ele(selector, timeout=Config.PAGE_LOAD_TIMEOUT)
        if not elem:
            raise ElementNotFoundError(f"{description}未找到: {selector}")
        elem.input(text)
        return True

    def _get_next_ipc(self):
        """获取下一个待处理的IPC"""
        # 先从日志文件获取最后处理的IPC
        if os.path.exists(Config.LOG_FILE):
            with open(Config.LOG_FILE, 'r') as f:
                lines = f.readlines()
                if lines:
                    return lines[-1].strip()

        # 从IPC列表文件获取
        if os.path.exists(Config.IPC_LIST_FILE):
            with open(Config.IPC_LIST_FILE, 'r') as f:
                for line in f:
                    ipc = line.strip()
                    if ipc and ipc not in self.processed_ipcs:
                        return ipc
        return Config.DEFAULT_IPC

    def _handle_pagination(self):
        """处理分页逻辑"""
        while True:
            try:
                # 处理当前页数据
                self._process_page()
                
                # 尝试翻页
                next_btn = self.browser.ele('xpath://a[@aria-label="下一页"]', timeout=5)
                if not next_btn:
                    logging.info("已到达最后一页")
                    break
                    
                self._safe_click('xpath://a[@aria-label="下一页"]', "下一页按钮")
                self.browser.wait.load_start()
                
            except Exception as e:
                logging.error(f"分页处理失败: {str(e)}")
                break

    def _process_page(self):
        """处理单页数据"""
        try:
            html = self.browser.html
            selector = Selector(html)
            rows = selector.xpath('//tbody[@id="resultListForm:resultTable_data"]/tr')
            
            if not rows:
                logging.warning("当前页面没有数据")
                return

            data_list = []
            for row in rows:
                # 数据解析逻辑（保持原有处理逻辑）
                data = {
                    'name': row.css('span.ps-patent-result--title--title::text').get('').strip(),
                    'pubdate': row.css('div.ps-patent-result--title--ctr-pubdate::text').get('').strip(),
                    'ipc': row.xpath('.//div[@id="resultListForm:resultTable:0:patentResult"]/@data-mt-ipc').get('').strip(),
                    # 其他字段解析...
                }
                data_list.append(data)
                
            self._save_data(data_list)
            
        except Exception as e:
            logging.error(f"页面数据处理失败: {str(e)}")
            raise

    def _save_data(self, data_list):
        """安全保存数据"""
        try:
            file_exists = os.path.exists(Config.DATA_FILE)
            with open(Config.DATA_FILE, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=data_list[0].keys() if data_list else [])
                if not file_exists:
                    writer.writeheader()
                writer.writerows(data_list)
        except Exception as e:
            logging.error(f"数据保存失败: {str(e)}")
            raise

    def _switch_ipc(self, new_ipc):
        """切换IPC分类"""
        try:
            logging.info(f"切换到新IPC分类: {new_ipc}")
            
            # 执行搜索操作
            self._safe_input('#advancedSearchForm:advancedSearchInput:input', f'IC:({new_ipc})', "搜索框")
            self._safe_click('#advancedSearchForm:advancedSearchInput:buttons', "搜索按钮")
            
            # 设置每页显示数量
            self._safe_click(f'@value={Config.PAGE_LIMIT}', "分页下拉")
            self.browser.wait.load_start()
            
            self.current_ipc = new_ipc
            with open(Config.LOG_FILE, 'a') as f:
                f.write(new_ipc + '\n')
                
        except Exception as e:
            logging.error(f"IPC切换失败: {str(e)}")
            raise

    def run(self):
        """主运行逻辑"""
        try:
            # 初始化浏览器
            self.browser.get('https://patentscope.wipo.int/search/zh/search.jsf')
            self._safe_click('@value=CLASSIF', "分类搜索按钮")
            
            # 主循环
            while True:
                current_ipc = self._get_next_ipc()
                if not current_ipc:
                    logging.info("所有IPC分类处理完成")
                    break
                    
                if current_ipc in self.processed_ipcs:
                    logging.info(f"IPC {current_ipc} 已处理，跳过")
                    continue
                    
                try:
                    self._switch_ipc(current_ipc)
                    self._handle_pagination()
                    self.processed_ipcs.add(current_ipc)
                except Exception as e:
                    logging.error(f"IPC {current_ipc} 处理失败，跳过")
                    continue

        finally:
            self.browser.quit()
            logging.info("爬虫正常终止")

# -------------------- 异常处理 --------------------
class CrawlerError(Exception):
    """基础异常类"""
    pass

class ElementNotFoundError(CrawlerError):
    """元素未找到异常"""
    pass

class PageLoadError(CrawlerError):
    """页面加载失败异常"""
    pass

# -------------------- 执行入口 --------------------
if __name__ == '__main__':
    setup_logging()
    try:
        crawler = WIPOCrawler()
        crawler.run()
    except KeyboardInterrupt:
        logging.info("用户中断操作")
    except Exception as e:
        logging.error(f"致命错误: {str(e)}")
        raise
