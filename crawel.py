import time
import pandas as pd
import os
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException

# --- 配置区域 ---
CHROMEDRIVER_PATH = r"D:\下载\chromedriver-win64\chromedriver-win64\chromedriver.exe" # ChromeDriver 路径 (使用原始字符串)
STOCK_CODE = "zssz399006" # 股票代码
BASE_URL = "https://guba.eastmoney.com" # 基础 URL
START_URL = f"{BASE_URL}/list,{STOCK_CODE}.html" # 起始列表页 URL
OUTPUT_CSV = f"guba_{STOCK_CODE}_comments_详细_v3.csv" # 输出 CSV 文件名 (更新版本号)
TARGET_SIZE_MB = 10 # 目标文件大小 (MB)
TARGET_SIZE_BYTES = TARGET_SIZE_MB * 1024 * 1024 # 目标文件大小 (Bytes)
WAIT_TIMEOUT = 0.1 # 元素等待超时时间 (秒) - 注意：这个值非常小，可能会导致频繁超时，建议适当增加（例如 5 或 10）
MAX_RETRIES_DETAIL_PAGE = 2 # 详情页加载失败的最大重试次数
page_num = 1 #开始页数
# --- 日志设置 ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# --- 辅助函数 ---
def get_current_data_size(filename):
    """检查文件大小 (Bytes)"""
    if os.path.exists(filename):
        return os.path.getsize(filename)
    return 0

# --- Selenium WebDriver 设置 ---
service = Service(executable_path=CHROMEDRIVER_PATH)
options = webdriver.ChromeOptions()
# options.add_argument('--headless')  # 无头模式运行 (通常更快) - 如果需要，取消注释
# options.add_argument('--disable-gpu') # 配合无头模式使用
# options.add_argument('--no-sandbox') # 在 Linux 环境中可能需要
# options.add_argument('--disable-dev-shm-usage') # 解决有限资源问题
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36") # 设置 User Agent
# 禁用图片加载，可能提升速度 (可选)
# options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})

driver = webdriver.Chrome(service=service, options=options)
logging.info("WebDriver 初始化完成.")

# --- CSS 选择器常量 ---
# 列表页选择器
LIST_TABLE_BODY_SELECTOR = "#mainlist > div > ul > li.defaultlist > table > tbody"
LIST_ITEM_SELECTOR = "tr.listitem"
LIST_ITEM_REPLY_SELECTOR = "td > div.reply"
LIST_ITEM_TITLE_DIV_SELECTOR = "td > div.title"
LIST_ITEM_TITLE_LINK_SELECTOR = "a" # 相对于 title_div
LIST_ITEM_AUTHOR_SELECTOR = "td > div.author > a.nametext"
LIST_ITEM_NEWS_TAG_SELECTOR = 'span.type_tag.zx.tag_1[title="资讯"]' # 相对于 title_div

# 详情页内容选择器 (多种结构)
CONTENT_SELECTOR_SHORT = "#newscontent > div.newstext" # 结构1: 短评论
CONTENT_SELECTOR_LONG_MODIFY = "div.xeditor_content.app_h5_modify" # 结构2: 长文章 (类型 modify)
CONTENT_SELECTOR_LONG_CFH_WEB = "#main > div.grid_wrapper > div.grid > div.g_content > div.article.page-article > div.article-body > div.xeditor_content.cfh_web" # 结构3: 长文章 (类型 cfh_web)
CONTENT_SELECTOR_LONG_ARTICLE_USER = "#main > div.grid_wrapper > div.grid > div.g_content > div.article.page-article > div.article-body > div.xeditor_content.app_h5_article" # 结构4: 长文章 (类型 app_h5_article)
# ***** 新增开始: 用户提供的第二个特定长文章结构 (article-body 容器) *****
CONTENT_SELECTOR_ARTICLE_BODY = "#main > div.grid_wrapper > div.grid > div.g_content > div.article.page-article > div.article-body" # 结构5: 直接定位 article-body 容器
# ***** 新增结束 *****


# --- 主要爬取逻辑 ---
all_data = [] # 存储当前批次抓取到的所有数据


try:
    while True:
        # --- 检查数据量是否达标 ---
        current_size = get_current_data_size(OUTPUT_CSV)
        if current_size >= TARGET_SIZE_BYTES:
            logging.info(f"目标数据量 ({TARGET_SIZE_MB} MB) 已达到. 停止爬取.")
            break

        # --- 构建列表页 URL ---
        if page_num == 1:
            list_url = START_URL
        else:
            list_url = f"{BASE_URL}/list,{STOCK_CODE}_{page_num}.html"

        logging.info(f"开始爬取列表页: {list_url}")

        try:
            driver.get(list_url)
            # 使用显式等待，等待列表主体加载完成
            # 注意：WAIT_TIMEOUT=0.1 可能太短，这里按原样保留，但建议调整
            wait = WebDriverWait(driver, WAIT_TIMEOUT ) # 稍微增加列表页的等待时间
            list_body = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, LIST_TABLE_BODY_SELECTOR)))
            logging.info("列表页加载完成. 正在查找帖子...")

            # 在已加载的列表主体中查找所有帖子行
            list_items = list_body.find_elements(By.CSS_SELECTOR, LIST_ITEM_SELECTOR)
            logging.info(f"在第 {page_num} 页找到 {len(list_items)} 个潜在帖子.")

            if not list_items:
                logging.warning(f"在第 {page_num} 页未找到帖子列表项. 可能已到达末页或页面结构变化.")
                break # 如果页面为空，则停止

            page_post_links = [] # 临时存储本页需要进一步抓取详情的帖子信息

            # --- 从列表页提取基本信息 ---
            for item in list_items:
                try:
                    # 检查是否为“资讯”类型的帖子，如果是则跳过
                    title_div = item.find_element(By.CSS_SELECTOR, LIST_ITEM_TITLE_DIV_SELECTOR)
                    try:
                        news_tag = title_div.find_element(By.CSS_SELECTOR, LIST_ITEM_NEWS_TAG_SELECTOR)
                        logging.debug("检测到'资讯'标签，跳过该帖子.")
                        continue
                    except NoSuchElementException:
                        pass # 不是资讯，继续

                    # 提取其他信息
                    reply_count_text = item.find_element(By.CSS_SELECTOR, LIST_ITEM_REPLY_SELECTOR).text
                    title_link_element = title_div.find_element(By.CSS_SELECTOR, LIST_ITEM_TITLE_LINK_SELECTOR)
                    title = title_link_element.get_attribute('title')
                    detail_url = title_link_element.get_attribute('href')
                    author = item.find_element(By.CSS_SELECTOR, LIST_ITEM_AUTHOR_SELECTOR).text

                    # 确保详情页 URL 是绝对路径
                    if detail_url and not detail_url.startswith('http'):
                        if detail_url.startswith('/'):
                            detail_url = BASE_URL + detail_url
                        else:
                            logging.warning(f"发现未知格式的相对 URL: {detail_url}，可能无法访问。跳过帖子 '{title}'.")
                            continue

                    if not detail_url:
                        logging.warning(f"帖子 '{title}' 缺少详情页链接，跳过。")
                        continue

                    page_post_links.append({
                        "title": title,
                        "author": author,
                        "replies": reply_count_text,
                        "detail_url": detail_url
                    })
                    logging.debug(f"提取列表信息: 标题='{title}', 作者='{author}', 链接='{detail_url}'")

                except NoSuchElementException as e:
                    logging.warning(f"在解析列表项时未找到某个元素: {e}")
                except StaleElementReferenceException:
                    logging.warning("列表页元素引用失效，可能页面已动态更新，跳过当前页的后续处理.")
                    break # 退出当前页的帖子处理

            # --- 爬取本页帖子的详情页内容 ---
            logging.info(f"开始处理来自第 {page_num} 页的 {len(page_post_links)} 个帖子的详情页...")
            for post_info in page_post_links:
                detail_url = post_info["detail_url"]
                content = "错误：无法获取内容" # 初始化内容为错误信息
                retries = 0

                while retries < MAX_RETRIES_DETAIL_PAGE:
                    content_element = None # 重置 content_element
                    found_structure = False # 标记是否找到已知结构
                    try:
                        logging.debug(f"导航至详情页: {detail_url}")
                        driver.get(detail_url)
                        # 详情页等待，使用配置的 WAIT_TIMEOUT
                        content_wait = WebDriverWait(driver, WAIT_TIMEOUT)

                        # --- 尝试按顺序定位多种可能的内容结构 ---
                        try:
                            # 尝试结构1: 短评论
                            logging.debug(f"尝试定位短评论结构 (1): {CONTENT_SELECTOR_SHORT}")
                            content_element = content_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, CONTENT_SELECTOR_SHORT)))
                            logging.info(f"找到内容结构 1 (短评论) @ {detail_url}")
                            found_structure = True
                        except (TimeoutException, NoSuchElementException):
                            logging.debug(f"未找到结构1，尝试长文章结构 (2): {CONTENT_SELECTOR_LONG_MODIFY}")
                            try:
                                # 尝试结构2: 长文章 (modify)
                                content_element = content_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, CONTENT_SELECTOR_LONG_MODIFY)))
                                logging.info(f"找到内容结构 2 (长文章 modify) @ {detail_url}")
                                found_structure = True
                            except (TimeoutException, NoSuchElementException):
                                logging.debug(f"未找到结构2，尝试长文章结构 (3): {CONTENT_SELECTOR_LONG_CFH_WEB}")
                                try:
                                    # 尝试结构3: 长文章 (cfh_web)
                                    content_element = content_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, CONTENT_SELECTOR_LONG_CFH_WEB)))
                                    logging.info(f"找到内容结构 3 (长文章 cfh_web) @ {detail_url}")
                                    found_structure = True
                                except (TimeoutException, NoSuchElementException):
                                    logging.debug(f"未找到结构3，尝试用户提供的长文章结构 (4): {CONTENT_SELECTOR_LONG_ARTICLE_USER}")
                                    try:
                                        # 尝试结构4: 长文章 (用户提供的 app_h5_article)
                                        content_element = content_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, CONTENT_SELECTOR_LONG_ARTICLE_USER)))
                                        logging.info(f"找到内容结构 4 (用户提供的 app_h5_article) @ {detail_url}")
                                        found_structure = True
                                    except (TimeoutException, NoSuchElementException):
                                        # ***** 新增开始: 尝试用户提供的第五种结构 (article-body container) *****
                                        logging.debug(f"未找到结构4，尝试用户提供的结构 (5 - article-body): {CONTENT_SELECTOR_ARTICLE_BODY}")
                                        try:
                                            # 尝试结构5: (article-body container)
                                            content_element = content_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, CONTENT_SELECTOR_ARTICLE_BODY)))
                                            logging.info(f"找到内容结构 5 (article-body container) @ {detail_url}")
                                            found_structure = True
                                        except (TimeoutException, NoSuchElementException):
                                            # 所有已知结构都未找到
                                            logging.warning(f"在 {detail_url} 上所有 ({5}) 种已知内容结构均未在 {WAIT_TIMEOUT} 秒内找到。帖子可能已删除、无内容或结构特殊。")
                                            # 注意：这里不立即 break 重试循环，让外层的 TimeoutException 或其他 Exception 处理重试逻辑。
                                            break
                                            # 如果真的是结构不存在，会在所有重试后判定失败。
                                        # ***** 新增结束 *****


                        # --- 处理找到的内容或最终错误 ---
                        if found_structure and content_element:
                            content = content_element.text # 获取元素的文本内容
                            if not content or content.isspace():
                                content = "内容为空或仅包含空格"
                                logging.debug(f"帖子 '{post_info['title']}' 内容为空.")
                            else:
                                logging.debug(f"成功获取内容: {post_info['title'][:30]}...")
                            break # 内容获取成功，退出重试循环

                        # 如果是因为结构确实找不到而设置了错误信息 (上面 warning 已经打出)
                        if not found_structure:
                            # 这里不需要设置错误文本，让重试机制继续
                            pass

                    except TimeoutException:
                        logging.warning(f"加载 {detail_url} 或等待元素超时。重试 ({retries+1}/{MAX_RETRIES_DETAIL_PAGE})...")
                        retries += 1
                        time.sleep(0.1) # 等待后重试 (稍微增加等待时间)
                    except Exception as e:
                        logging.error(f"获取 {detail_url} 内容时发生意外错误: {e}。重试 ({retries+1}/{MAX_RETRIES_DETAIL_PAGE})...")
                        retries += 1
                        time.sleep(0.1) # 等待后重试

                    # 如果循环是因为重试次数耗尽而结束
                    if retries >= MAX_RETRIES_DETAIL_PAGE:
                        # 检查是否是因为一直找不到元素（而不是因为 Timeout 等其他异常）
                        if not found_structure: # 并且在上面的try块中没有设置content_element
                            content = f"错误：重试后仍未找到已知内容元素 (已尝试{5}种结构)" # 更新尝试的结构数量
                            logging.error(f"获取 {detail_url} 内容失败，多次重试后仍未找到已知结构。")
                        # else: 如果 found_structure 为 True 但仍然失败退出循环（不太可能，除非 .text 出错），
                        # 或者是因为 Timeout 等异常退出重试循环，保留 content 的初始值 "错误：无法获取内容" 或最后一次循环设置的值
                        elif content == "错误：无法获取内容": # 确保如果是因为超时等退出，也有个错误信息
                            content = "错误：获取内容重试次数已达上限，可能因超时或未知错误"
                            logging.error(f"获取 {detail_url} 内容重试次数已达上限，最终失败（可能超时）。")

                        break # 退出重试循环


                # 添加完整记录到数据列表
                all_data.append({
                    "标题": post_info["title"],
                    "作者": post_info["author"],
                    "评论数": post_info["replies"],
                    "正文": content,
                    "链接": detail_url # 保存 URL 以便追踪
                })
                # 短暂休眠，避免请求过于频繁



            # --- 定期保存数据 ---
            if all_data:
                df = pd.DataFrame(all_data)
                file_exists = os.path.exists(OUTPUT_CSV)
                df.to_csv(OUTPUT_CSV, mode='a' if file_exists else 'w', index=False, header=not file_exists, encoding='utf-8-sig')
                saved_count = len(all_data)
                all_data = [] # 清空列表
                current_size_mb = get_current_data_size(OUTPUT_CSV) / 1024 / 1024
                logging.info(f"已将 {saved_count} 条新数据追加到 {OUTPUT_CSV}. 当前总大小: {current_size_mb:.2f} MB")

            # 再次检查大小，确保在保存后能及时停止
            if get_current_data_size(OUTPUT_CSV) >= TARGET_SIZE_BYTES:
                logging.info(f"在处理完第 {page_num} 页后，数据量达到目标. 停止爬取.")
                break

        except TimeoutException:
            logging.error(f"加载列表页 {list_url} 超时. 跳过此页.")
            time.sleep(1.5)
        except Exception as e:
            logging.error(f"处理第 {page_num} 页时发生未预料的错误: {e}")


        # --- 前往下一页 ---
        page_num += 1
        # time.sleep(random.uniform(0.5, 1.5)) # 可选延迟


except KeyboardInterrupt:
    logging.info("用户手动中断爬取.")
except Exception as e:
    logging.error(f"发生严重错误，爬虫意外终止: {e}", exc_info=True) # exc_info=True 打印堆栈信息
finally:
    # --- 清理工作 ---
    if 'driver' in locals() and driver:
        driver.quit()
        logging.info("WebDriver 已关闭.")

    # --- 最后一次保存 ---
    if all_data:
        logging.info("执行最后的数据保存...")
        df = pd.DataFrame(all_data)
        file_exists = os.path.exists(OUTPUT_CSV)
        df.to_csv(OUTPUT_CSV, mode='a' if file_exists else 'w', index=False, header=not file_exists, encoding='utf-8-sig')
        final_size_mb = get_current_data_size(OUTPUT_CSV) / 1024 / 1024
        logging.info(f"最终保存完成. 文件最终大小: {final_size_mb:.2f} MB")

    logging.info("爬虫程序执行结束.")