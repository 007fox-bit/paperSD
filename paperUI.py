import streamlit as st
import pandas as pd
from serpapi import GoogleSearch
import requests
import os
import re
import zipfile
import shutil
import time
import random
import tempfile

# ================= 页面配置 =================
st.set_page_config(
    page_title="Scholar Fetcher Pro",
    page_icon="🌊",
    layout="wide"
)


# ================= 核心功能函数 =================

def sanitize_filename(title):
    """清洗文件名"""
    clean_title = re.sub(r'[\\/*?:"<>|]', "", str(title))
    clean_title = clean_title.replace('\n', ' ').strip()
    return clean_title[:80]  # 限制长度


def is_likely_journal(pub_info_str):
    """判断是否为期刊 (简单规则)"""
    if not pub_info_str: return False
    text = pub_info_str.lower()
    conference_keywords = ["conference", "proceedings", "symposium", "workshop", "meeting"]
    for kw in conference_keywords:
        if kw in text: return False
    return True


def search_scholar(api_key, query, num_results, start_year, end_year, only_journals):
    """执行 SerpApi 搜索"""
    results_list = []
    start_offset = 0
    max_retries = 3
    empty_streak = 0

    status_text = st.empty()
    progress_bar = st.progress(0)

    while len(results_list) < num_results:
        # 更新进度显示
        current_progress = min(len(results_list) / num_results, 0.95)
        progress_bar.progress(current_progress)
        status_text.text(f"正在搜索... 已获取 {len(results_list)}/{num_results} 条")

        params = {
            "engine": "google_scholar",
            "q": query,
            "api_key": api_key,
            "hl": "zh-CN",
            "num": 20,
            "start": start_offset
        }

        if start_year and end_year:
            params["as_ylo"] = start_year
            params["as_yhi"] = end_year

        try:
            search = GoogleSearch(params)
            data = search.get_dict()

            if "error" in data:
                st.error(f"API 错误: {data['error']}")
                break

            organic_results = data.get("organic_results", [])

            if not organic_results:
                empty_streak += 1
                if empty_streak >= max_retries: break
            else:
                empty_streak = 0

            for item in organic_results:
                if len(results_list) >= num_results: break

                pub_info = item.get("publication_info", {}).get("summary", "")

                # 期刊筛选逻辑
                if only_journals and not is_likely_journal(pub_info):
                    continue

                pdf_link = "N/A"
                if "resources" in item:
                    for res in item["resources"]:
                        if "file_format" in res and "PDF" in res.get("file_format"):
                            pdf_link = res.get("link")
                            break
                        # 有些情况 resources 里直接就是 link
                        if not pdf_link and res.get("link", "").endswith(".pdf"):
                            pdf_link = res.get("link")

                paper = {
                    "Title": item.get("title"),
                    "Authors_Source": pub_info,
                    "Year": item.get("publication_info", {}).get("authors", {}),  # 简单获取，可能不准
                    "Link": item.get("link"),
                    "Citations": item.get("inline_links", {}).get("cited_by", {}).get("total", 0),
                    "PDF_Link": pdf_link
                }
                results_list.append(paper)

            start_offset += 20
            time.sleep(0.5)  # 避免请求过快

        except Exception as e:
            st.error(f"发生异常: {e}")
            break

    progress_bar.progress(1.0)
    status_text.text(f"搜索完成！共找到 {len(results_list)} 条结果。")
    return pd.DataFrame(results_list)


def download_and_zip_pdfs(df):
    """下载 PDF 并打包成 ZIP"""

    # 创建临时目录
    with tempfile.TemporaryDirectory() as temp_dir:
        pdf_dir = os.path.join(temp_dir, "pdfs")
        os.makedirs(pdf_dir)

        success_count = 0
        total_tasks = len(df)

        my_bar = st.progress(0)
        status_txt = st.empty()

        for index, row in df.iterrows():
            title = row['Title']
            url = row['PDF_Link']

            # 更新进度
            my_bar.progress((index + 1) / total_tasks)
            status_txt.text(f"正在处理 [{index + 1}/{total_tasks}]: {title[:30]}...")

            if not url or url == "N/A":
                continue

            safe_name = sanitize_filename(title)
            file_path = os.path.join(pdf_dir, f"{index + 1:03d}_{safe_name}.pdf")

            try:
                headers = {'User-Agent': "Mozilla/5.0 Chrome/91.0.4472.124"}
                r = requests.get(url, headers=headers, stream=True, timeout=10)
                if r.status_code == 200 and int(r.headers.get('Content-Length', 10000)) > 2000:
                    with open(file_path, 'wb') as f:
                        for chunk in r.iter_content(8192):
                            f.write(chunk)
                    success_count += 1
                    time.sleep(random.uniform(1, 2))  # 随机延时
            except:
                pass

        # 打包成 ZIP
        zip_path = os.path.join(temp_dir, "papers_bundle.zip")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(pdf_dir):
                for file in files:
                    zipf.write(os.path.join(root, file), file)

        # 读取 ZIP 内容到内存以便下载
        with open(zip_path, "rb") as f:
            zip_data = f.read()

        return zip_data, success_count


# ================= 侧边栏：设置 =================
with st.sidebar:
    st.header("⚙️ 设置")
    api_key = st.text_input("输入 SerpApi Key", type="password", help="请去 serpapi.com 注册获取")

    st.markdown("---")

    keyword = st.text_input("搜索关键词", value="underwater slam")

    col1, col2 = st.columns(2)
    with col1:
        start_year = st.number_input("开始年份", 2020, 2030, 2021)
    with col2:
        end_year = st.number_input("结束年份", 2020, 2030, 2025)

    num_results = st.slider("获取数量", 10, 100, 20, step=10)
    only_journals = st.checkbox("尝试仅筛选期刊 (排除会议)", value=True)

    search_btn = st.button("🚀 开始搜索", use_container_width=True)

# ================= 主界面 =================
st.title("🌊 水下机器人文献获取助手")
st.markdown("快速搜索 Google Scholar，导出 Excel 并一键下载 PDF。")

# 初始化 session state 用于存储搜索结果
if 'search_data' not in st.session_state:
    st.session_state.search_data = None

# --- 逻辑 1: 点击搜索 ---
if search_btn:
    if not api_key:
        st.warning("⚠️ 请先在侧边栏输入 SerpApi Key")
    else:
        with st.spinner('正在连接谷歌学术...'):
            df = search_scholar(api_key, keyword, num_results, start_year, end_year, only_journals)
            if not df.empty:
                st.session_state.search_data = df
            else:
                st.error("未找到相关数据，请检查关键词或网络。")

# --- 逻辑 2: 展示结果与下载 ---
if st.session_state.search_data is not None:
    df = st.session_state.search_data

    st.divider()
    st.subheader(f"📊 搜索结果 ({len(df)} 篇)")

    # 1. 显示表格
    st.dataframe(
        df,
        column_config={
            "Link": st.column_config.LinkColumn("谷歌学术链接"),
            "PDF_Link": st.column_config.LinkColumn("PDF 下载链接"),
            "Citations": st.column_config.NumberColumn("引用数")
        },
        use_container_width=True
    )

    col_d1, col_d2 = st.columns([1, 2])

    # 2. 下载 CSV 按钮
    with col_d1:
        csv = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 导出结果为 CSV",
            data=csv,
            file_name=f"scholar_results_{keyword}.csv",
            mime="text/csv",
            use_container_width=True
        )

    # 3. 批量下载 PDF 逻辑
    with col_d2:
        st.info("💡 提示：只有含直接 PDF 链接的文献才能下载 (Open Access)。")
        if st.button("📦 批量下载 PDF 并打包 (可能需要几分钟)", use_container_width=True):
            if df['PDF_Link'].eq("N/A").all():
                st.error("当前结果中没有可直接下载的 PDF 链接。")
            else:
                with st.spinner("正在后台下载 PDF，请勿刷新页面..."):
                    zip_bytes, count = download_and_zip_pdfs(df)

                    if count > 0:
                        st.success(f"成功打包 {count} 个 PDF 文件！")
                        st.download_button(
                            label="⬇️ 点击下载 PDF 压缩包 (.zip)",
                            data=zip_bytes,
                            file_name=f"papers_{keyword}.zip",
                            mime="application/zip"
                        )
                    else:
                        st.warning("尝试下载失败，可能因反爬虫或链接失效。建议手动点击表格中的链接下载。")

# 页脚
st.markdown("---")
st.caption("Powered by Streamlit & SerpApi | 此工具仅供科研学习使用")