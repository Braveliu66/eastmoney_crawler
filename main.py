import csv
import jieba
import nltk
from nltk.util import ngrams
from collections import Counter

import string
import csv
import os
import re

original_file_path = 'data.csv'
row_removal_string = '错误：无法获取内容'
url_pattern = re.compile(r"https?://\S+")
temp_file_path = original_file_path + '.temp'

rows_processed = 0
rows_removed = 0
rows_kept = 0

print(f"开始处理文件: {original_file_path}")
print(f"- 将删除第四列内容为 '{row_removal_string}' 的行。")
print(f"- 将从保留行的第四列中删除所有URL。")

try:
    with open(original_file_path, 'r', encoding='utf-8', newline='') as infile, \
            open(temp_file_path, 'w', encoding='utf-8', newline='') as outfile:

        reader = csv.reader(infile)
        writer = csv.writer(outfile)
        for row in reader:
            rows_processed += 1
            keep_row = True
            if len(row) >= 4 and row[3] == row_removal_string:
                keep_row = False
                rows_removed += 1

            elif len(row) >= 4:

                text_to_clean = row[3]
                cleaned_text = url_pattern.sub('', text_to_clean)#清洗正文,去除网址
                row[3] = cleaned_text

            if keep_row:
                writer.writerow(row)
                rows_kept += 1

    os.replace(temp_file_path, original_file_path)
    print("\n处理完成。")
    print(f"原始文件 '{original_file_path}' 已被修改。")

except FileNotFoundError:
    print(f"错误: 文件 '{original_file_path}' 未找到。请确保文件存在且路径正确。")
    if os.path.exists(temp_file_path):
        os.remove(temp_file_path)
        print(f"临时文件 '{temp_file_path}' 已删除。")
except Exception as e:
    print(f"处理文件时发生错误: {e}")
    if os.path.exists(temp_file_path):
        os.remove(temp_file_path)
        print(f"错误发生，临时文件 '{temp_file_path}' 已删除。原始文件可能未被修改或不完整。")
finally:
    if os.path.exists(temp_file_path):
        try:
            os.remove(temp_file_path)
            print(f"清理：残留的临时文件 '{temp_file_path}' 已删除。")
        except OSError as oe:
            print(f"警告：无法删除临时文件 '{temp_file_path}': {oe}")

csv_file_path = 'data.csv'

# --- 文本清洗配置 ---
# 包含了常见的中文和英文标点，以及空格、制表符、换行符
punctuation_set = set("＂＃＄％＆＇（）＊＋，－／：；＜＝＞＠［＼］＾＿｀｛｜｝～｟｠｢｣､　、〃〈〉《》「」『』【】〔〕〖〗〘〙〚〛〜〝〞〟〰〾〿–—‘’‛“”„‟…‧﹏﹑﹔·！？｡。") | set(string.punctuation) | set([' ', '\t', '\n', '\r', '　', '$', '#']) # 添加了 $, # 和全角空格

# 定义正则表达式，用于匹配常见的股票代码模式
stock_code_pattern = re.compile(r'^(sh|sz|hk)\d{5,6}$', re.IGNORECASE)

# --- 数据加载与分词 ---
all_tokens = []  # 创建一个空列表，用于存储所有文本分词后的 词语

print(f"开始处理文件: {csv_file_path}")
try:
    with open(csv_file_path, 'r', encoding='utf-8') as file:

        reader = csv.reader(file)
        # 逐行读取CSV文件
        for i, row in enumerate(reader):
            # 检查行是否至少有4列数据
            if len(row) >= 4:
                # 提取第4列的文本内容
                main_text = row[3]

                # 使用jieba进行分词
                tokens = list(jieba.cut(main_text, cut_all=False))

                # --- 文本清洗步骤 ---
                cleaned_tokens = [] # 存储当前行清洗后的词语
                for token in tokens:
                    # 1. 去除首尾空白字符
                    token = token.strip()
                    # 2. 跳过空字符串
                    if not token:
                        continue
                    # 3. 跳过纯标点符号或我们定义的特殊符号
                    if token in punctuation_set:
                        continue
                    # 4. 跳过纯数字组成的词语
                    if token.isdigit():
                        continue
                    # 5. 跳过匹配股票代码模式的词语
                    if stock_code_pattern.match(token):
                        continue

                    cleaned_tokens.append(token)

                # 将当前行清洗后的词语列表追加到总列表 all_tokens 中
                all_tokens.extend(cleaned_tokens)
            else:
                # 打印警告信息并跳过格式不符的行
                print(f"警告: 第 {i+1} 行数据格式不符 (只有 {len(row)} 列)，已跳过。内容: {row}")

    print(f"文件读取、分词和清洗完成。总共提取了 {len(all_tokens)} 个有效词语。")

except FileNotFoundError:
    # 处理文件未找到错误
    print(f"错误: 文件 '{csv_file_path}' 未找到。请检查文件路径是否正确。")
    exit()
except Exception as e:
    # 处理其他可能的错误
    print(f"处理文件时发生错误: {e}")
    exit()

# --- 构建Bi-gram模型 ---
print("开始构建Bi-gram模型...")

# 检查是否有足够的词语来生成bi-gram
if len(all_tokens) < 2:
    print("错误: 清洗后剩余的总词语数量不足（少于2个），无法生成Bi-gram。")
else:
    # 使用nltk生成bi-gram
    bi_grams_list = list(ngrams(all_tokens, 2))
    print(f"成功生成了 {len(bi_grams_list)} 个Bi-gram。")

    # 使用Counter统计bi-gram频率
    bi_gram_counts = Counter(bi_grams_list)

    # --- 输出结果 ---
    print("\n出现频率最高的 20 个 Bi-gram 及其频率:")
    # 获取并打印频率最高的20个bi-gram
    for bi_gram, count in bi_gram_counts.most_common(20):
        print(f"('{bi_gram[0]}', '{bi_gram[1]}'): {count}")

print("\n所有处理完成。")