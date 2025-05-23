import os
import pickle
import time
from datetime import datetime

import numpy as np
import requests
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# API KEY 및 파일 경로 설정
KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")
UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOOK_CHUNK_DIR = os.path.join(BASE_DIR, "book_chunk")

# Solar Embeddings 설정
solar_client = OpenAI(
    api_key=UPSTAGE_API_KEY, base_url="https://api.upstage.ai/v1/solar"
)

# 검색할 키워드 리스트 정의
search_keywords = [
    "업적",
    "능력",
    "협업심",
    "리더십",
    "태도",
    "경영",
    "자기계발",
    "성공",
    "비즈니스",
    "인문",
    "소설",
    "과학",
    "예술",
    "역사",
    "철학",
    "심리",
    "교육",
    "문화",
    "정치",
    "경제",
    "창의성",
    "책임감",
    "효율성",
    "리더십",
    "협업",
    "정확성",
    "적응력",
    "분석력",
    "열정",
    "신뢰성",
    "시간관리",
    "투명성",
    "결정력",
    "성실성",
    "문제해결",
    "전문성",
    "의사소통",
    "동기부여",
    "감정지능",
    "팀워크",
    "멘토링",
    "자기계발",
    "유연성",
    "갈등관리",
    "목표달성",
    "학습",
    "공감",
    "창조성",
    "전략",
]


def cosine_similarity(vec1, vec2):
    return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))


def fetch_books_by_keyword(keyword, total_count=300):
    """키워드로 도서를 검색하는 함수"""
    url = "https://dapi.kakao.com/v3/search/book"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}

    all_books = []
    page = 1

    while len(all_books) < total_count:
        params = {
            "query": keyword,
            "size": min(50, total_count - len(all_books)),
            "page": page,
            "target": "title",
        }

        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            break

        result = response.json()
        books = result.get("documents", [])
        if not books:
            break

        all_books.extend(books)
        page += 1

    return all_books


from functools import lru_cache


@lru_cache(maxsize=1000)
def create_embedding(text, max_retries=3, base_timeout=10):
    """텍스트의 임베딩을 생성하는 함수 (캐싱 적용, 재시도 메커니즘 포함)"""
    for attempt in range(max_retries):
        start_time = time.time()
        timeout = base_timeout * (attempt + 1)  # 재시도마다 타임아웃 증가

        try:
            embedding_response = solar_client.embeddings.create(
                input=text, model="embedding-passage"
            )

            processing_time = time.time() - start_time
            if processing_time > timeout:
                print(
                    f"\n경고: 임베딩 처리 시간 초과 ({processing_time:.2f}초), 재시도 {attempt + 1}/{max_retries}"
                )
                continue

            # 캐싱을 위해 tuple로 변환
            return tuple(embedding_response.data[0].embedding)

        except Exception as e:
            print(f"\n임베딩 생성 중 오류 발생 ({attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(1)  # 재시도 전 잠시 대기
                continue
            return None

    return None


def load_existing_books():
    """청크 파일들로부터 모든 도서 데이터를 로드하는 함수"""
    all_books = {}

    for chunk_file in os.listdir(BOOK_CHUNK_DIR):
        if chunk_file.startswith("books_chunk_") and chunk_file.endswith(".pkl"):
            try:
                with open(os.path.join(BOOK_CHUNK_DIR, chunk_file), "rb") as f:
                    chunk_data = pickle.load(f)
                    all_books.update(chunk_data)
            except Exception as e:
                print(f"경고: 청크 파일 '{chunk_file}' 로드 중 오류 발생: {str(e)}")

    return all_books


def load_progress():
    """진행 상황을 로드하는 함수"""
    try:
        with open("progress.pkl", "rb") as f:
            return pickle.load(f)
    except FileNotFoundError:
        return {
            "completed_keywords": set(),  # 처리 완료된 키워드 집합
            "last_processed_chunk": None,  # 마지막으로 처리된 청크 ID
            "completed_chunks": set(),  # 처리 완료된 청크 집합
        }


def save_progress(progress):
    """진행 상황을 저장하는 함수"""
    with open("progress.pkl", "wb") as f:
        pickle.dump(progress, f)


def process_and_save_books_in_chunks():
    """청크 단위로 도서 정보를 처리하는 함수"""
    chunk_size = 1000
    processed_isbns = set()
    total_processed = 0
    keyword_stats = {}

    # 저장 디렉토리 생성
    os.makedirs(BOOK_CHUNK_DIR, exist_ok=True)

    print("\n=== 도서 정보 수집 시작 ===")
    print(f"청크 크기: {chunk_size}")

    # 기존 처리된 ISBN 로드 부분 수정
    print("\n1. 기존 처리된 도서 정보 로드 중...")
    for chunk_file in tqdm(os.listdir(BOOK_CHUNK_DIR), desc="청크 파일 검사"):
        if chunk_file.startswith("books_chunk_") and chunk_file.endswith(".pkl"):
            try:
                with open(os.path.join(BOOK_CHUNK_DIR, chunk_file), "rb") as f:
                    chunk_data = pickle.load(f)
                    processed_isbns.update(chunk_data.keys())
            except Exception as e:
                print(f"경고: 청크 파일 '{chunk_file}' 로드 중 오류 발생: {str(e)}")

    print(f"- 기존 처리된 도서 수: {len(processed_isbns)}개")

    # 중복 키워드 제거
    unique_keywords = list(dict.fromkeys(search_keywords))
    print(f"\n2. 처리할 키워드: {len(unique_keywords)}개")
    print(f"- 키워드 목록: {', '.join(unique_keywords)}")

    try:
        chunk_number = len(
            [f for f in os.listdir(BOOK_CHUNK_DIR) if f.startswith("books_chunk_")]
        )
        print(f"\n3. 청크 처리 시작 (현재 청크 번호: {chunk_number})")

        for keyword_idx, keyword in enumerate(unique_keywords, 1):
            print(
                f"\n=== 키워드 {keyword_idx}/{len(unique_keywords)}: '{keyword}' 처리 중 ==="
            )
            current_chunk = {}
            keyword_stats[keyword] = {"total": 0, "new": 0, "processed": 0}

            # 키워드로 도서 검색
            books = fetch_books_by_keyword(keyword)
            keyword_stats[keyword]["total"] = len(books)
            print(f"- 검색된 도서: {len(books)}개")

            new_books = 0
            processed_in_keyword = 0
            with tqdm(books, desc="도서 처리", unit="권") as pbar:
                for book in pbar:
                    isbn = book.get("isbn", "").split(" ")[0]
                    if not isbn or isbn in processed_isbns:
                        continue

                    current_chunk[isbn] = book

                    # 청크 크기에 도달하면 처리 및 저장
                    if len(current_chunk) >= chunk_size:
                        print("\n- 청크 처리 중...")
                        processed_chunk = process_chunk(list(current_chunk.values()))
                        if processed_chunk:
                            save_chunk(processed_chunk, chunk_number)
                            processed_isbns.update(processed_chunk.keys())
                            processed_in_keyword += len(processed_chunk)
                            new_books += len(processed_chunk)
                            total_processed += len(processed_chunk)
                            chunk_number += 1
                        current_chunk = {}

            # 남은 데이터 처리
            if current_chunk:
                print("\n- 남은 도서 처리 중...")
                processed_chunk = process_chunk(list(current_chunk.values()))
                if processed_chunk:
                    save_chunk(processed_chunk, chunk_number)
                    processed_isbns.update(processed_chunk.keys())
                    processed_in_keyword += len(processed_chunk)
                    total_processed += len(processed_chunk)
                    chunk_number += 1

            keyword_stats[keyword].update(
                {"new": new_books, "processed": processed_in_keyword}
            )

            print(f"키워드 '{keyword}' 처리 완료")

    except KeyboardInterrupt:
        print("\n\n=== 사용자에 의해 중단됨 ===")
        if current_chunk:
            print("- 마지막 청크 저장 중...")
            processed_chunk = process_chunk(list(current_chunk.values()))
            if processed_chunk:
                save_chunk(processed_chunk, chunk_number)
                total_processed += len(processed_chunk)

    except Exception as e:
        print(f"\n\n=== 오류 발생 ===")
        print(f"오류 내용: {str(e)}")
        if current_chunk:
            print("- 마지막 청크 저장 중...")
            processed_chunk = process_chunk(list(current_chunk.values()))
            if processed_chunk:
                save_chunk(processed_chunk, chunk_number)
                total_processed += len(processed_chunk)

    finally:
        print("\n=== 처리 완료 ===")
        print(f"- 총 처리된 새로운 도서: {total_processed}개")
        print(f"- 전체 저장된 도서: {len(processed_isbns)}개")
        print(f"- 생성된 청크 파일 수: {chunk_number}개")


def find_similar_books(query_text, top_k=5):
    """쿼리와 가장 유사한 도서를 찾는 함수"""
    all_books_data = load_existing_books()

    query_embedding = create_embedding(query_text)
    if not query_embedding:
        return []

    similarities = []
    for isbn, book_data in all_books_data.items():
        similarity = np.dot(query_embedding, book_data["embedding"]) / (
            np.linalg.norm(query_embedding) * np.linalg.norm(book_data["embedding"])
        )
        similarities.append((similarity, book_data))

    return sorted(similarities, key=lambda x: x[0], reverse=True)[:top_k]


from concurrent.futures import ThreadPoolExecutor


def process_single_book(book, max_retries=3):
    """단일 도서 처리 및 임베딩 생성 (재시도 포함)"""
    process_start_time = time.time()

    isbn = book.get("isbn", "").split(" ")[0]
    if not isbn:
        return None, "skip"

    contents = book.get("contents", "")
    if not contents:
        return None, "skip"

    for attempt in range(max_retries):
        # 임베딩 생성 (캐싱 적용)
        embedding = create_embedding(contents)
        if embedding:
            return {
                "isbn": isbn,
                "title": book.get("title"),
                "authors": book.get("authors"),
                "publisher": book.get("publisher"),
                "contents": contents,
                "thumbnail": book.get("thumbnail"),
                "embedding": list(embedding),  # tuple을 list로 변환
                "timestamp": datetime.now().isoformat(),
                "processing_time": time.time() - process_start_time,
                "attempts": attempt + 1,
            }, "success"

        print(
            f"\n임베딩 생성 실패 ({attempt + 1}/{max_retries}){', 재시도 중...' if attempt < max_retries - 1 else ', 최대 시도 횟수 초과'}"
        )
        if attempt < max_retries - 1:
            time.sleep(1)

    return None, "timeout"


def process_chunk(books):
    """도서 데이터를 병렬로 처리하고 임베딩을 생성하는 함수"""
    chunk_data = {}
    books_list = list(books)  # dict_values를 리스트로 변환
    total_books = len(books_list)
    success_count = skip_count = timeout_count = 0

    if total_books == 0:
        return chunk_data

    # 시스템 CPU 코어 수에 따라 worker 수 조정
    max_workers = min(os.cpu_count() or 4, 8)  # 최대 8개

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 배치 크기 조정
        batch_size = 15
        for i in range(0, total_books, batch_size):
            batch = books_list[i : i + batch_size]

            # 배치 단위로 병렬 처리
            futures = [executor.submit(process_single_book, book) for book in batch]

            # 결과 수집
            for future in tqdm(
                futures,
                desc=f"배치 처리 중 ({i+1}-{min(i+batch_size, total_books)}/{total_books})",
                unit="권",
            ):
                try:
                    result, status = future.result(timeout=30)  # 타임아웃 설정

                    if status == "success" and result is not None:
                        chunk_data[result["isbn"]] = result
                        success_count += 1
                    elif status == "skip":
                        skip_count += 1
                    else:  # timeout
                        timeout_count += 1

                except Exception as e:
                    print(f"\n도서 처리 중 오류 발생: {str(e)}")
                    timeout_count += 1

    # 처리 결과 출력
    print(f"\n청크 처리 결과:")
    print(f"- 전체 도서: {total_books}권")
    print(f"- 성공: {success_count}권")
    print(f"- 건너뛰기: {skip_count}권")
    print(f"- 시간초과: {timeout_count}권")

    return chunk_data


def save_chunk(books_chunk, chunk_number):
    """청크 데이터를 파일로 저장하는 함수"""
    if books_chunk:  # 청크에 데이터가 있는 경우에만 저장
        chunk_filename = os.path.join(BOOK_CHUNK_DIR, f"books_chunk_{chunk_number}.pkl")
        with open(chunk_filename, "wb") as f:
            pickle.dump(books_chunk, f)
        print(f"청크 {chunk_number} 저장 완료 (도서 {len(books_chunk)}개)")


if __name__ == "__main__":
    start_time = datetime.now()
    print(f"처리 시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    process_and_save_books_in_chunks()

    end_time = datetime.now()
    processing_time = end_time - start_time
    print(f"\n총 처리 시간: {processing_time}")
