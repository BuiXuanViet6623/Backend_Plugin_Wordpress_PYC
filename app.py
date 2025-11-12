import os
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request
from datetime import datetime

app = Flask(__name__)
MAX_CONCURRENT = 10  # số chương crawl cùng lúc

def log_json(book_id, book_title, chapter_id, chapter_title, status, message=""):
    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "book_id": book_id,
        "book_title": book_title,
        "chapter_id": chapter_id,
        "chapter_title": chapter_title,
        "status": status,
        "message": message
    }
    print(log_entry)

async def fetch(session, url):
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None, resp.status
            return await resp.text(), resp.status
    except Exception as e:
        return None, str(e)

async def get_chapter_content(session, book_id, chapter_id, book_title, chapter_title):
    url = f"https://www.qimao.com/shuku/{book_id}-{chapter_id}/"
    html, status = await fetch(session, url)
    if html is None:
        log_json(book_id, book_title, chapter_id, chapter_title, "error", f"{status}")
        return ""
    soup = BeautifulSoup(html, "html.parser")
    article = soup.find("div", class_="article")
    if not article:
        log_json(book_id, book_title, chapter_id, chapter_title, "error", "Không tìm thấy div.article")
        return ""
    paragraphs = article.find_all("p")
    content = "\n".join([p.get_text(strip=True) for p in paragraphs])
    log_json(book_id, book_title, chapter_id, chapter_title, "success", f"Đã crawl {len(paragraphs)} đoạn")
    return content

async def crawl_books_and_chapters_async():
    all_books = []
    book_api = "https://www.qimao.com/qimaoapi/api/classify/book-list"
    params = {"channel":"a","category1":"a","category2":"a","words":"a",
              "update_time":"a","is_vip":"a","is_over":"a","order":"click","page":1}

    async with aiohttp.ClientSession() as session:
        async with session.get(book_api, params=params) as resp:
            data = await resp.json()
    books = data.get("data", {}).get("book_list", [])[:5]

    async with aiohttp.ClientSession() as session:
        for book in books:
            book_data = {
                "book_id": book['book_id'],
                "title": book['title'],
                "category": book.get('category2_name',''),
                "description": book.get('intro',''),
                "cover_image": book.get('image_link',''),
                "author": book.get('author',''),
                "chapters":[]
            }

            # Lấy 5 chương
            chapter_api = f"https://www.qimao.com/qimaoapi/api/book/chapter-list?book_id={book['book_id']}"
            async with session.get(chapter_api) as resp:
                chapters_resp = await resp.json()
            chapters = chapters_resp.get("data", {}).get("chapters", [])[:5]

            # Crawl tất cả chương song song nhưng giới hạn concurrency
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)
            async def crawl_with_sem(ch):
                async with semaphore:
                    return ch, await get_chapter_content(session, book['book_id'], ch['id'], book['title'], ch['title'])

            tasks = [crawl_with_sem(ch) for ch in chapters]
            results = await asyncio.gather(*tasks)

            for ch, content in results:
                book_data['chapters'].append({
                    "id": ch['id'],
                    "title": ch['title'],
                    "words": ch['words'],
                    "is_vip": ch['is_vip'],
                    "content": content
                })

            all_books.append(book_data)

    return all_books

@app.route("/", methods=["GET"])
def home():
    return "API Running"

@app.route("/crawl", methods=["GET"])
def crawl_api():
    data = asyncio.run(crawl_books_and_chapters_async())

    # Chuẩn hóa JSON cho plugin
    results = []
    for book in data:
        results.append({
    "title": book['title'],
    "author": book['author'],
    "cover_image": book.get('cover_image',''),  # đúng key rồi
    "description": book.get('description',''),
    "genres": [book.get('category','')],
    "chapters": [
        {
            "title": ch['title'],
            "content": ch['content']
        } for ch in book['chapters']
    ]
})


    return jsonify({"results": results})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
