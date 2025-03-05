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
                    logging.warning(f"尝试 {attempt}/{retries} 失败: {str(e)}. {delay}秒后重试...")
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
        """安全点击元素（与原代码完全一致）"""
        elem = self.browser.ele(selector, timeout=Config.PAGE_LOAD_TIMEOUT)
        if not elem:
            raise ElementNotFoundError(f"{description}未找到: {selector}")
        self.browser.scroll.to_see(elem)
        elem.click()
        time.sleep(Config.ACTION_DELAY)
        return True

    @retry(retries=Config.MAX_RETRY, delay=5)
    def _safe_input(self, selector, text, description="输入框"):
        """安全输入文本（与原代码完全一致）"""
        elem = self.browser.ele(selector, timeout=Config.PAGE_LOAD_TIMEOUT)
        if not elem:
            raise ElementNotFoundError(f"{description}未找到: {selector}")
        elem.clear()
        elem.input(text)
        time.sleep(Config.ACTION_DELAY)
        return True

    def _get_next_ipc(self):
        """获取下一个IPC（与原代码逻辑一致）"""
        # 从日志文件获取最后处理的IPC
        if os.path.exists(Config.LOG_FILE):
            with open(Config.LOG_FILE, 'r') as f:
                lines = f.readlines()
                if lines:
                    return lines[-1].strip().replace(' ', '')
        
        # 从IPC列表文件获取
        if os.path.exists(Config.IPC_LIST_FILE):
            with open(Config.IPC_LIST_FILE, 'r') as f:
                lines = [line.strip() for line in f if line.strip()]
                if lines:
                    return lines[0].replace(' ', '')
        return Config.DEFAULT_IPC

    def _process_page(self):
        """处理页面数据（保持原代码解析逻辑）"""
        try:
            html = self.browser.html
            selector = Selector(html)
            rows = selector.xpath('//tbody[@id="resultListForm:resultTable_data"]/tr')
            logging.info(f"当前页找到 {len(rows)} 条数据")
            
            data_list = []
            for ele in rows:
                data_dict = {
                    'name': ele.css('span.ps-patent-result--title--title.content--text-wrap::text').get('').strip(),
                    'data_rk': ele.css('tr::attr(data-rk)').get(''),
                    'data_ri': ele.css('tr::attr(data-ri)').get(''),
                    'ipc': ele.xpath('.//div[@id="resultListForm:resultTable:0:patentResult"]/@data-mt-ipc').get('').strip(),
                    'pubdate': ele.css('div.ps-patent-result--title--ctr-pubdate::text').get('').strip(),
                    'serial_number': ele.css('span.notranslate.ps-patent-result--title--record-number::text').get('').strip(),
                    'detail_url': 'https://patentscope.wipo.int/search/zh/' + ele.css('div.ps-patent-result--first-row a::attr(href)').get(''),
                    'application_number': ele.xpath('.//span[contains(text(), "申请号")]/following-sibling::span/text()').get('').strip(),
                    'application_people': ele.xpath('.//span[contains(text(), "申请人")]/following-sibling::span/text()').get('').strip(),
                    'inventor': ele.xpath('.//span[contains(text(), "发明人")]/following-sibling::span/text()').get('').strip(),
                    'introduction': ele.xpath('.//span[@class="trans-section needTranslation-biblio"]/text()').get('').strip(),
                }
                data_list.append(data_dict)
            
            self._save_data(data_list)
            return True
        except Exception as e:
            logging.error(f"数据处理失败: {str(e)}")
            raise

    def _save_data(self, data_list):
        """保存数据（与原代码完全一致）"""
        if not data_list:
            return

        file_exists = os.path.exists(Config.DATA_FILE)
        fieldnames = data_list[0].keys()

        try:
            with open(Config.DATA_FILE, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerows(data_list)
        except Exception as e:
            logging.error(f"数据保存失败: {str(e)}")
            raise

    def _handle_pagination(self):
        """分页处理（保持原代码翻页逻辑）"""
        while True:
            try:
                # 处理当前页
                self._process_page()
                
                # 获取下一页按钮
                next_btn = self.browser.ele('xpath://a[@aria-label="下一页"]', timeout=5)
                if not next_btn:
                    logging.info("已到达最后一页")
                    break
                
                # 执行翻页
                self._safe_click('xpath://a[@aria-label="下一页"]', "下一页按钮")
                self.browser.wait.load_start()
                time.sleep(Config.ACTION_DELAY)
                
            except Exception as e:
                logging.error(f"分页失败: {str(e)}")
                break

    def _switch_ipc(self, new_ipc):
        """切换IPC分类（完全还原原代码操作流程）"""
        logging.info(f"正在切换至IPC分类: {new_ipc}")
        
        try:
            # 初始化页面状态
            self.browser.get('https://patentscope.wipo.int/search/zh/search.jsf')
            self._safe_click('@value=CLASSIF', "分类搜索按钮")
            
            # 输入IPC并搜索
            self._safe_input('#simpleSearchForm:fpSearch:input', new_ipc, "IPC输入框")
            self._safe_click('#simpleSearchForm:fpSearch:buttons', "搜索按钮")
            self.browser.wait.load_start()
            
            # 设置分页大小
            self._safe_click(f'@value={Config.PAGE_LIMIT}', "分页下拉")
            self.browser.wait.load_start()
            
            # 记录处理进度
            with open(Config.LOG_FILE, 'a') as f:
                f.write(new_ipc + '\n')
                
            # 从列表移除已处理IPC
            self._remove_processed_ipc(new_ipc)
            
        except Exception as e:
            logging.error(f"IPC切换失败: {str(e)}")
            raise

    def _remove_processed_ipc(self, ipc):
        """从IPC列表移除已处理项（与原代码逻辑一致）"""
        try:
            if os.path.exists(Config.IPC_LIST_FILE):
                with open(Config.IPC_LIST_FILE, 'r') as f:
                    lines = [line.strip() for line in f]
                
                with open(Config.IPC_LIST_FILE, 'w') as f:
                    f.write('\n'.join(line for line in lines if line.replace(' ', '') != ipc.replace(' ', '')))
        except Exception as e:
            logging.error(f"IPC列表更新失败: {str(e)}")

    def run(self):
        """主运行逻辑（优化后的流程）"""
        try:
            while True:
                current_ipc = self._get_next_ipc()
                if not current_ipc:
                    logging.info("所有IPC分类处理完成")
                    break
                
                if current_ipc in self.processed_ipcs:
                    logging.info(f"跳过已处理IPC: {current_ipc}")
                    continue
                
                logging.info(f"开始处理IPC分类: {current_ipc}")
                try:
                    self._switch_ipc(current_ipc)
                    self._handle_pagination()
                    self.processed_ipcs.add(current_ipc)
                except Exception as e:
                    logging.error(f"IPC处理失败: {current_ipc}, 错误: {str(e)}")
                    continue
        finally:
            self.browser.quit()
            logging.info("爬虫进程正常终止")

# -------------------- 异常处理 --------------------
class CrawlerError(Exception):
    """基础异常类"""
    pass

class ElementNotFoundError(CrawlerError):
    """元素未找到异常"""
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
        logging.critical(f"程序异常终止: {str(e)}")
        raise
