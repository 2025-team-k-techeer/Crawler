import os
import re
import csv
import time
import requests
from PIL import Image
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime

today = datetime.today().strftime("%Y-%m-%d")

IMAGE_DIR = "danawa_images"
os.makedirs(IMAGE_DIR, exist_ok=True)


# 다나와의 썸네일 이미지의 해상도 조절을 위한 코드
def upgrade_image_url(url):
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    # 파라미터 수동 수정
    query["shrink"] = ["330:*"]

    # 다시 조합
    new_query = urlencode(query, doseq=True)
    upgraded_url = urlunparse(parsed._replace(query=new_query))
    return upgraded_url


def extract_dimensions(text):
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)(?:\s*cm)?",
        text,
    )

    if match:
        return match.group(1), match.group(2), match.group(3)
    return "", "", ""


def download_image(url, filename):
    try:
        if not url or "noImg" in url:
            return ""  # ❌ 대체 이미지 URL은 무시

        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content)).convert("RGB")  # 알파 채널 제거
            img.verify()  # ✅ 이미지 검증 (깨진 이미지 방지)
            img = Image.open(BytesIO(response.content)).convert("RGB")  # 알파 채널 제거
            save_path = os.path.join(IMAGE_DIR, filename)
            img.save(save_path, format="JPEG")
            return save_path
    except Exception as e:
        print(f"⚠️ 이미지 저장 실패: {e}")
    return ""


def crawl_danawa(keyword="책상", category="desk", max_items=10000):
    options = Options()
    options.binary_location = "C:/Program Files/Google/Chrome/Application/chrome.exe"  # Windows용 Chrome 실행 경로

    # options.add_experimental_option("detach", True)  # 창이 꺼지지 않도록 유지
    options.add_argument("--headless")  # 창이 안 뜨던 원인! 주석 유지
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )

    base_url = f"https://search.danawa.com/dsearch.php?query={keyword}&originalQuery={keyword}&cate=&srchMethod=top&volumeType=allvs&page="
    data = []
    count = 0

    for page in range(1, 10):
        if count >= max_items:
            break

        url = f"{base_url}{page}"
        driver.get(url)
        time.sleep(2)

        # 그리고 WebDriverWait도 이렇게
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "ul.product_list > li"))
        )

        soup = BeautifulSoup(driver.page_source, "html.parser")
        products = soup.select("ul.product_list > li")  # ✅ 기존 방식

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

                # 상세 페이지 접근 → 크기 추출
                driver.get(product_url)
                time.sleep(1.5)

                # ✅ 썸네일 목록에서 첫 번째 이미지 추출
                thumbnail_elements = driver.find_elements(
                    By.CSS_SELECTOR, "div.thumb_w img"
                )

                images = []
                for thumb in thumbnail_elements:
                    thumb_src = thumb.get_attribute("src")
                    if not thumb_src or "noImg" in thumb_src:
                        continue
                    # 썸네일에서 원본 이미지로 추정 경로 변경
                    image_url = thumb_src.replace("thumb", "prod_img")

                    image_url = (
                        "https:" + image_url
                        if image_url.startswith("//")
                        else image_url
                    )

                    image_url = upgrade_image_url(image_url)
                    images.append(image_url)

                # img_tag = item.select_one("a.thumb_link > img")
                # raw_url = (
                #     img_tag.get("data-original")
                #     if img_tag and img_tag.has_attr("data-original")
                #     else img_tag.get("src")
                # )
                # if not raw_url or "noImg" in raw_url:
                #     continue  # ❌ 대체 이미지 건너뜀

                # image_url = "https:" + raw_url if raw_url.startswith("//") else raw_url

                # 안전한 파일 생성
                image_paths = []
                for idx, image_url in enumerate(images, 1):
                    safe_name = re.sub(r'[\\/*?:"<>|]', "", name).replace(" ", "_")
                    filename = f"{safe_name}_{idx}.jpg"
                    image_path = download_image(image_url, filename)
                    if image_path:  # 다운로드 성공한 경우만 저장
                        image_paths.append(image_path)

                # 물품 크기 추출
                product_soup = BeautifulSoup(driver.page_source, "html.parser")
                spec_text = product_soup.get_text()
                width, depth, height = extract_dimensions(spec_text)

                # ✅ image_urls, image_paths를 문자열로 병합하여 저장
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

    driver.quit()

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
    crawl_danawa(keyword="책상", category="desk")
