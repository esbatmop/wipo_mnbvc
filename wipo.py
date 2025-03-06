import time
import sys
import csv
from DrissionPage import ChromiumPage
from parsel import Selector
import os

# 配置常量
DEFAULT_IPC = 'A23P20/17'
URL = 'https://patentscope.wipo.int/search/zh/search.jsf'
PAGE_LIMIT = 200

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

current_dir = get_base_dir()
base_dir = os.path.dirname(current_dir)
LOG_FILE = os.path.join(base_dir, 'wipo_ipcs_list_logs.txt')
DATA_FILE = os.path.join(base_dir, 'wipo_data.csv')
IPC_LIST_FILE = os.path.join(base_dir, 'wipo_ipcs_list.txt')

web = ChromiumPage()

def get_last_ipc():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
            return lines[-1].strip().replace(' ', '') if lines else None
    return None

def initialize_web():
    web.get(URL)
    web.ele('@value=CLASSIF').click()
    web.ele('#simpleSearchForm:fpSearch:input').input(get_last_ipc() or DEFAULT_IPC, clear=True)
    web.ele('#simpleSearchForm:fpSearch:buttons').click()
    time.sleep(5)
    web.ele('@value=200', -1).click()
    web.wait.load_start()
    print('开始爬取')

def add_to_logs(ipc_):
    with open(LOG_FILE, 'a') as f:
        f.write(ipc_ + '\n')

def remove_from_logs(ipc_):
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w') as f:
            f.write('')
    with open(LOG_FILE, 'r') as f:
        lines = f.readlines()
    with open(LOG_FILE, 'w') as f:
        f.writelines([line for line in lines if line.strip() != ipc_])

def pop_from_list():
    if os.path.exists(IPC_LIST_FILE):
        with open(IPC_LIST_FILE, 'r') as f:
            lines = f.readlines()
        if lines:
            ipc_ = lines[0].strip()
            with open(IPC_LIST_FILE, 'w') as f:
                f.writelines(lines[1:])
            return ipc_
    return None

def handle_data(html):
    text = Selector(html)
    eles = text.xpath('//tbody[@id="resultListForm:resultTable_data"]/tr')
    print(f'大小 {len(eles)}')
    try:
        page = text.css('.ps-paginator--page--value').xpath('string(.)').get().strip()
    except:
        page = "没有数据"
    
    data_list = []
    for ele in eles:
        # 解析数据的代码保持不变...
        # ...（此处省略解析代码，与原代码相同）
        
        data_dict = {
            'name': name,
            'data_rk': data_rk,
            'data_ri': data_ri,
            'ipc': ipc,
            'pubdate': pubdate,
            'serial_number': serial_number,
            'detail_url': detail_url,
            'application_number': application_number,
            'application_people': application_people,
            'inventor': inventor,
            'page': page,
            'introduction': introduction
        }
        data_list.append(data_dict)
    
    save_data_to_file(data_list)
    return page

def save_data_to_file(data_list):
    if not data_list:
        return
    file_exists = os.path.exists(DATA_FILE)
    fieldnames = data_list[0].keys()
    
    with open(DATA_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(data_list)

if __name__ == '__main__':
    initialize_web()
    
    ipc_ = get_last_ipc() or DEFAULT_IPC
    while True:
        # 处理当前页面
        current_html = web.html
        current_page = handle_data(current_html)
        print(f"处理完成: {current_page}")
        
        # 检查是否有下一页
        next_btn = web.ele('xpath://a[@aria-label="下一页"]', timeout=5)
        if next_btn:
            next_btn.click()
            web.wait.load_start()
            time.sleep(2)
        else:
            # 切换IPC
            print(f'移除IPC: {ipc_}')
            remove_from_logs(ipc_)
            ipc_ = pop_from_list()
            if not ipc_:
                print("没有更多IPC，结束爬取")
                break
            
            print(f'读取新IPC: {ipc_}')
            add_to_logs(ipc_)
            # 重新输入IPC进行搜索
            search_box = web.ele('#advancedSearchForm:advancedSearchInput:input')
            search_box.input('IC:(' + ipc_.replace(' ', '') + ')', clear=True, by_js=True)
            search_box.parent().ele('button[type="submit"]').click()
            web.wait.load_start()
            time.sleep(5)
            
        time.sleep(2)
