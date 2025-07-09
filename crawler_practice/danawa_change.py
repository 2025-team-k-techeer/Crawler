import os
import re
import csv
import time
import requests
from PIL import Image
from io import BytesIO
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode
from datetime import datetime

today = datetime.today().strftime("%Y-%m-%d")
IMAGE_DIR = "danawa_images"
os.makedirs(IMAGE_DIR, exist_ok=True)


def upgrade_image_url(url):
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query["shrink"] = ["330:*"]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def extract_dimensions(text):
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)(?:\s*cm)?",
        text,
    )
    return match.groups() if match else ("", "", "")


def download_image(url, filename, image_dir):
    try:
        if not url or "noImg" in url:
            return ""
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content)).convert("RGB")
            img.verify()
            img = Image.open(BytesIO(response.content)).convert("RGB")
            save_path = os.path.join(image_dir, filename)
            img.save(save_path, format="JPEG")
            return save_path
    except Exception as e:
        print(f"⚠️ 이미지 저장 실패: {e}")
    return ""


def crawl_danawa(keyword="책상", category="desk", max_items=1000):
    data = []
    count = 0

    headers = {"User-Agent": "Mozilla/5.0"}

    image_dir = os.path.join(IMAGE_DIR, category)
    os.makedirs(image_dir, exist_ok=True)

    for page in range(1, 10):
        if count >= max_items:
            break

        search_url = f"https://search.danawa.com/dsearch.php?query={keyword}&originalQuery={keyword}&cate=&srchMethod=top&volumeType=allvs&page={page}"
        response = requests.get(search_url, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")
        products = soup.select("ul.product_list > li")

        print(f"[Page {page}] 상품 수: {len(products)}")

        for item in products:
            if count >= max_items:
                break
            try:
                name_tag = item.select_one("p.prod_name > a")
                if not name_tag:
                    continue

                name = name_tag.text.strip()
                product_url = name_tag["href"]

                # 상세 페이지 접근 (정적)
                detail_response = requests.get(product_url, headers=headers)
                detail_soup = BeautifulSoup(detail_response.text, "html.parser")

                # 썸네일 이미지 추출
                images = []
                for img_tag in detail_soup.select("div.thumb_w img"):
                    src = img_tag.get("src", "")
                    if "noImg" in src or not src:
                        continue
                    src = "https:" + src if src.startswith("//") else src
                    image_url = upgrade_image_url(src.replace("thumb", "prod_img"))
                    images.append(image_url)

                # 이미지 다운로드
                image_paths = []
                for idx, image_url in enumerate(images, 1):
                    safe_name = re.sub(r'[\\/*?:"<>|]', "", name).replace(" ", "_")
                    filename = f"{safe_name}_{idx}.jpg"
                    image_path = download_image(image_url, filename, image_dir)
                    if image_path:
                        image_paths.append(image_path)

                # 크기 정보 추출
                text = detail_soup.get_text()
                width, depth, height = extract_dimensions(text)

                data.append(
                    [
                        name,
                        product_url,
                        ";".join(images),
                        ";".join(image_paths),
                        width,
                        depth,
                        height,
                        category,
                    ]
                )
                print(f"✔ {name} 저장 완료")
                count += 1

            except Exception as e:
                print(f"⚠️ 에러 발생: {e}")
                continue

    csvfilename = f"danawa_{category}_{today}.csv"
    with open(csvfilename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "name",
                "product_url",
                "image_url",
                "image_path",
                "width",
                "depth",
                "height",
                "category",
            ]
        )
        writer.writerows(data)

    print(f"✅ {csvfilename} 저장 완료")


if __name__ == "__main__":
    crawl_danawa(keyword="침대", category="bed")
