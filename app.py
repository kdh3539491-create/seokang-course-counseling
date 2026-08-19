from pathlib import Path
import csv
import re
import streamlit as st
from openai import OpenAI

# =========================================================
# 기본 설정
# =========================================================

st.set_page_config(
    page_title="서강고 선택과목 AI 상담",
    page_icon="🎓",
    layout="centered",
)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

MODEL = "gpt-5.6-terra"

# =========================================================
# API 연결
# =========================================================

try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
except Exception:
    st.error(
        "OpenAI API 키가 설정되지 않았습니다. "
        "Streamlit의 Settings → Secrets에서 OPENAI_API_KEY를 확인해주세요."
    )
    st.stop()

# =========================================================
# CSV 불러오기
# =========================================================

def load_csv(filename):
    path = DATA_DIR / filename

    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


school_2025 = load_csv("school_2025.csv")
school_2026 = load_csv("school_2026.csv")
university_rules = load_csv("university_rules.csv")
university_scope = load_csv("university_scope.csv")
source_status_2029 = load_csv("source_status_2029.csv")
source_audit = load_csv("source_audit.csv")

# =========================================================
# 문자열 처리
# =========================================================

def normalize(text):
    return re.sub(
        r"[^0-9a-zA-Z가-힣]",
        "",
        (text or "").lower()
    )


UNIVERSITY_ALIASES = {
    "서울대": "서울대학교",
    "연세대": "연세대학교",
    "고려대": "고려대학교",
    "서강대": "서강대학교",
    "성균관대": "성균관대학교",
    "한양대": "한양대학교",
    "중앙대": "중앙대학교",
    "경희대": "경희대학교",
    "이화여대": "이화여자대학교",
    "전남대": "전남대학교",
    "전북대": "전북대학교",
    "충남대": "충남대학교",
    "충북대": "충북대학교",
    "부산대": "부산대학교",
    "경북대": "경북대학교",
    "강원대": "강원대학교",
    "조선대": "조선대학교",
}


def university_aliases_for(name):
    """대학명에 캠퍼스 표기가 붙어 있어도 약칭/정식명을 같은 대학으로 인식한다."""
    aliases = {name}
    name_norm = normalize(name)

    for short, full in UNIVERSITY_ALIASES.items():
        short_norm = normalize(short)
        full_norm = normalize(full)

        if (
            name_norm == short_norm
            or name_norm == full_norm
            or short_norm in name_norm
            or full_norm in name_norm
        ):
            aliases.add(short)
            aliases.add(full)

    return aliases


def university_is_mentioned(university, user_text):
    """'전남대/전남대학교' 입력을 '전남대학교(광주)' 같은 CSV 행과 연결한다."""
    text_norm = normalize(user_text)
    university_norm = normalize(university)

    if not university_norm:
        return False

    if university_norm in text_norm:
        return True

    for alias in university_aliases_for(university):
        alias_norm = normalize(alias)
        if alias_norm and alias_norm in text_norm:
            return True

    for short, full in UNIVERSITY_ALIASES.items():
        short_norm = normalize(short)
        full_norm = normalize(full)

        if short_norm in text_norm or full_norm in text_norm:
            if short_norm in university_norm or full_norm in university_norm:
                return True

    return False


# =========================================================
# 학생 질문에서 대학/학과 관련 공식 DB 찾기
# =========================================================

def find_relevant_university_rules(user_text):
    text_norm = normalize(user_text)

    # -----------------------------------------------------
    # 1. 질문에 등장한 대학 식별
    # -----------------------------------------------------
    mentioned_universities = []

    for row in university_rules:
        university = (row.get("대학") or "").strip()

        if not university:
            continue

        if university_is_mentioned(university, user_text):
            if university not in mentioned_universities:
                mentioned_universities.append(university)

    # -----------------------------------------------------
    # 2. 모집단위별 점수 계산
    # -----------------------------------------------------
    scored = []

    for row in university_rules:
        university = (row.get("대학") or "").strip()
        major = (row.get("모집단위") or "").strip()
        keywords = row.get("검색키워드") or ""

        # 특정 대학이 확인되면 그 대학 자료만 남긴다.
        if mentioned_universities:
            if university not in mentioned_universities:
                continue

        major_terms = []

        if major:
            major_terms.append(major)

        if keywords:
            major_terms.extend(
                [
                    x.strip()
                    for x in keywords.split("|")
                    if x.strip()
                ]
            )

        score = 0

        # 공식 모집단위명이 질문에 그대로 있으면 최우선
        major_norm = normalize(major)
        if major and major_norm in text_norm:
            score += 100

        # 학생 표현과 공식 모집단위명이 일부만 겹치는 경우도 후보로 남긴다.
        # 예: '화학공학과' ↔ '화공생명공학과'
        if major_norm:
            common_major_terms = [
                "화학공학", "화공", "생명공학", "기계공학", "전기전자",
                "전자공학", "컴퓨터", "소프트웨어", "신소재", "재료공학",
                "건축", "토목", "환경", "수학", "통계", "물리", "화학",
                "생명과학", "의예", "약학", "간호", "경영", "경제",
                "심리", "교육", "국어", "영어", "역사", "철학"
            ]
            for term in common_major_terms:
                term_norm = normalize(term)
                if term_norm in text_norm and term_norm in major_norm:
                    score += 35

        # 검색 키워드 매칭
        for term in major_terms:
            term_norm = normalize(term)

            if not term_norm:
                continue

            if term_norm in text_norm:
                # 긴 키워드일수록 신뢰도를 높인다.
                score += 20 + len(term_norm)

        # 대학명만 확인된 경우에도 최소 후보에는 남긴다.
        if mentioned_universities and university in mentioned_universities:
            score += 5

        if score > 0:
            scored.append((score, row))

    scored.sort(
        key=lambda x: x[0],
        reverse=True
    )

    # 상위 10개만 모델에 전달
    return [row for score, row in scored[:10]]


# =========================================================
# 전국 대학 범위 검색
# =========================================================

def find_scope_matches(user_text):
    text_norm = normalize(user_text)
    found = []

    for row in university_scope:
        university = (row.get("대학") or "").strip()

        if not university:
            continue

        if university_is_mentioned(university, user_text):
            found.append(row)

    return found[:10]


# =========================================================
# 학교 교육과정 문자열 생성
# =========================================================

def school_curriculum_text(grade):
    rows = school_2026 if grade == "1학년" else school_2025

    if not rows:
        return "학교 교육과정 DB를 불러오지 못했습니다."

    grouped = {}

    for row in rows:
        semester = row.get("학기", "")
        grouped.setdefault(semester, []).append(row)

    sections = []

    for semester, items in grouped.items():
        if not items:
            continue

        selection_count = items[0].get("선택수", "")
        sections.append(
            f"\n[{semester} / 택{selection_count}]"
        )

        for item in items:
            mandatory = (
                " / 정보·제2외국어·한문 의무교과군"
                if item.get("의무교과군") == "Y"
                else ""
            )

            note = (
                f" / {item.get('비고')}"
                if item.get("비고")
                else ""
            )

            sections.append(
                f"- {item.get('과목명')} "
                f"({item.get('교과군')}, {item.get('과목유형')}"
                f"{mandatory}{note})"
            )

    return "\n".join(sections)


# =========================================================
# 공식 대학자료 문자열 생성
# =========================================================

def university_evidence_text(rows):
    if not rows:
        return (
            "현재 구조화된 대학 공식 권장과목 DB에서 "
            "질문과 직접 일치하는 자료를 찾지 못했습니다."
        )

    result = []

    for r in rows:
        result.append(
            f"""
대학: {r.get('대학', '')}
모집단위: {r.get('모집단위', '')}
적용학년도: {r.get('적용학년도', '')}
자료상태: {r.get('자료상태', '')}
구분: {r.get('구분', '')}
핵심과목: {r.get('핵심과목', '') or '미지정'}
권장과목: {r.get('권장과목', '') or '미지정'}
추가조건: {r.get('추가조건', '') or '없음'}
출처기관: {r.get('출처기관', '')}
출처명: {r.get('출처명', '')}
공식URL: {r.get('출처URL', '')}
발표일: {r.get('발표일', '')}
비고: {r.get('비고', '')}
""".strip()
        )

    return "\n\n".join(result)


# =========================================================
# 시스템 지침
# =========================================================

SYSTEM_INSTRUCTIONS = """
너는 '서강고 선택과목 AI 상담'이다.

주요 사용자는 서강고등학교 1·2학년 학생이다.

학년 분기:
- 현재 1학년 = 2026학년도 입학생 = 2029학년도 대입
- 현재 2학년 = 2025학년도 입학생 = 2028학년도 대입

학생의 현재 학년이 아직 확인되지 않았다면
다른 상담보다 먼저 반드시 1학년인지 2학년인지 묻는다.

이미 학년을 말했다면 다시 묻지 않는다.

[서강고 강제 규칙]

1. 매 학기 정보/제2외국어/한문 교과군에서 정확히 1과목을 선택해야 한다.
   - 0과목 불가
   - 정확히 1과목 필수
   - 2과목 이상 불가

2. 동일한 과목은 서로 다른 학기에도 중복 이수할 수 없다.
   예: 1학기에 화학을 선택했다면 2학기에 화학을 다시 선택할 수 없다.

3. 학기별 택N을 반드시 지켜야 한다.

4. 서강고 교육과정에 실제 개설되지 않은 과목을
   학생이 선택할 수 있는 것처럼 말하지 않는다.

[서강고 권장사항]

3학년 과목 중
- 화법과 언어
- 확률과 통계

는 수능 학습과 직접 관련되어 학생들이 많이 선택하는 과목이므로
특별한 이유가 없다면 기본 추천안에 우선 고려한다.

그러나 이것은 강제조건이나 대학 필수과목이 아니다.

대학의 핵심 전공연계과목이나 학생의 학업계획과 충돌한다면
장단점을 비교해서 설명한다.

[대학 입시자료]

입시정보 신뢰도 우선순위:

1. 해당 대학 입학처 공식자료
2. 한국대학교육협의회 및 대입정보포털 어디가
3. 교육부·교육청 공식자료

입시학원, 블로그, 카페, SNS, 커뮤니티의 정보만으로
대학 공식 기준을 단정하지 않는다.

공식자료가 없으면 추측하지 말고
'현재 확보된 공식자료에서는 확인하지 못했습니다.'
라고 답한다.

[2029 상담]

1학년은 2029 대입 대상이다.

2029 대학별 공식 세부자료가 있다면 그것을 최우선 사용한다.

아직 없다면 2028 해당 대학 공식자료를 참고할 수 있으며,
이 경우 반드시 다음 사실을 명시한다.

'2028 공식자료 참고 / 2029 미확정'

중요:
현재 DB에서 2028 공식자료가 검색되었다면,
2029 공식자료가 아직 없다는 이유만으로
'권장과목 자료가 없다'고 답하지 않는다.

반드시 검색된 2028 공식자료의 권장과목을 학생에게 알려준 뒤
그 자료가 2029 확정 기준은 아니라는 점을 별도로 설명한다.

2028 기준이 2029에도 그대로 유지될 것이라고 단정하지 않는다.

[2028 상담]

2학년은 2028 대입 대상이다.

2028 대학 공식 시행계획, 전공연계과목,
권장이수과목, 핵심권장과목, 반영과목,
가점·평가기준을 직접 적용한다.

[권장과 필수]

다음을 엄격히 구분한다.

- 지원자격
- 필수과목
- 핵심 권장과목
- 권장과목
- 전공연계과목
- 반영과목
- 가점
- 참고과목

'권장'을 '필수'라고 표현하지 않는다.

권장과목을 이수하지 않았다는 이유만으로
지원 불가나 불합격을 단정하지 않는다.

[검색된 자료 사용 원칙]

질문과 관련하여 구조화 DB에서 공식자료가 검색되었다면
그 자료를 답변에서 우선적으로 활용한다.

대학명이나 학과명이 학생 표현과 공식 모집단위 명칭이 조금 다르더라도
검색 결과가 명확하게 해당 학과를 가리키면 그 자료를 사용한다.

예:
학생이 '고려대 화학공학과'라고 표현했는데
검색 결과가 '고려대 화공생명공학과'로 확인되면,
'고려대의 공식 모집단위명은 화공생명공학과입니다.'라고 짧게 안내하고
해당 학과의 권장과목 자료를 사용한다.

검색 결과가 여러 개라서 학과를 확정하기 어렵다면
임의로 하나를 고르지 말고 학생에게 한 번 확인한다.

[구조화 DB 우선 원칙]

현재 질문에서 대학과 모집단위가 명확하고 구조화 DB에서 해당 행이 검색되었다면,
그 행의 핵심과목·권장과목·추가조건을 최우선 사실로 사용한다.

검색된 공식자료가 있는데도
'공식자료가 없다', 'DB에 없다', '확인할 수 없다'고 답하지 않는다.

예:
고려대 컴퓨터학과 행이 검색되고 핵심과목이 '미적분Ⅱ, 기하'라면
반드시 그 내용을 고려대 컴퓨터학과의 검색된 공식자료로 안내한다.

모델의 일반 지식이나 추정으로 검색된 DB 내용을 덮어쓰지 않는다.

[상담 방식]

학생과 자연스럽게 대화한다.

상담에 필요한 정보 중 아직 없는 것만 질문한다.

주요 정보:
- 현재 학년
- 희망 대학 또는 대학군
- 희망 학과·전공
- 관심 진로
- 현재 고민 중인 선택과목
- 이미 이수하거나 선택한 과목

질문을 한꺼번에 너무 많이 하지 않는다.

학생이 이미 제공한 정보는 다시 묻지 않는다.

[여러 대학]

학생이 여러 대학을 희망하면 단순 나열하지 말고

- 공통 권장과목
- 대학별 차이
- 서강고에서 실제 가능한 조합
- 진로 변경 가능성

을 종합한다.

[전국 대학]

서울권뿐 아니라
수도권, 국가거점국립대, 지역 국립대,
지방 사립대, 의약학계열 등 국내 대학 전체를 상담한다.

[출처]

대학 공식정보를 사용한 경우 가능하면 답변 끝에

- 대학명
- 자료명
- 적용학년도
- 공식 발표기관

을 간단히 표시한다.

확인하지 않은 출처를 만들어내지 않는다.

[한계]

이 서비스는 학생의 선택과목 결정을 지원하는 상담 도구다.

대학 합격·불합격을 판정하지 않는다.

정보가 부족하면 억지로 답하지 않는다.

최종 과목 선택은 담임교사 또는 교육과정 담당교사와 확인하도록 안내한다.

[개인정보]

학생의 이름, 학번, 전화번호, 주소 등
상담에 불필요한 개인정보를 요구하지 않는다.

[주제 제한]

이 서비스의 목적은
고등학교 선택과목, 대학 전공, 대입 준비 관련 상담이다.

학생이 게임, 연예, 투자, 정치, 소설 작성 등
상담 목적과 무관한 질문을 하면

'이 상담 서비스는 선택과목 및 대입 상담 전용입니다.'

라고 짧게 안내하고 본래 상담으로 유도한다.
"""

# =========================================================
# 세션 상태 초기화
# =========================================================

if "messages" not in st.session_state:
    st.session_state.messages = []

if "grade" not in st.session_state:
    st.session_state.grade = None

if "question_count" not in st.session_state:
    st.session_state.question_count = 0

# =========================================================
# 화면 상단
# =========================================================

st.title("🎓 서강고 선택과목 AI 상담")

st.caption(
    "서강고 교육과정과 대학 공식 입시자료를 바탕으로 "
    "선택과목을 상담합니다."
)

with st.expander("상담 이용 안내"):
    st.write(
        """
- 현재 1학년은 2029학년도 대입 기준으로 상담합니다.
- 현재 2학년은 2028학년도 대입 기준으로 상담합니다.
- 이름·학번 등 개인정보는 입력하지 않아도 됩니다.
- 대학의 권장과목은 지원 필수조건과 다를 수 있습니다.
- 최종 선택은 담임 또는 교육과정 담당교사와 확인하세요.
        """
    )

# =========================================================
# 대화 초기 안내
# =========================================================

if not st.session_state.messages:
    greeting = (
        "안녕하세요. 서강고 선택과목 상담을 시작하겠습니다. 😊\n\n"
        "**먼저 현재 1학년인가요, 2학년인가요?**"
    )

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": greeting
        }
    )

# =========================================================
# 이전 대화 표시
# =========================================================

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# =========================================================
# 상담 초기화 버튼
# =========================================================

with st.sidebar:
    st.markdown("## 상담 설정")

    st.write(
        f"사용 모델: **GPT-5.6 Terra**"
    )

    if st.session_state.grade:
        target_year = (
            "2029학년도"
            if st.session_state.grade == "1학년"
            else "2028학년도"
        )

        st.success(
            f"{st.session_state.grade} / {target_year} 대입"
        )

    st.write(
        f"현재 상담 질문 수: "
        f"{st.session_state.question_count}/20"
    )

    if st.button("🔄 새 상담 시작"):
        st.session_state.messages = []
        st.session_state.grade = None
        st.session_state.question_count = 0
        st.rerun()

# =========================================================
# 학생 질문 입력
# =========================================================

user_input = st.chat_input(
    "궁금한 내용을 입력하세요."
)

if user_input:

    # 질문 길이 제한
    if len(user_input) > 1500:
        st.warning(
            "질문이 너무 깁니다. "
            "1,500자 이내로 줄여주세요."
        )
        st.stop()

    # 질문 횟수 제한
    if st.session_state.question_count >= 20:
        st.warning(
            "한 번의 상담은 최대 20회 질문까지 가능합니다. "
            "새 상담을 시작해주세요."
        )
        st.stop()

    st.session_state.question_count += 1

    # 학년 자동 감지
    if st.session_state.grade is None:

        if (
            "1학년" in user_input
            or "일학년" in user_input
        ):
            st.session_state.grade = "1학년"

        elif (
            "2학년" in user_input
            or "이학년" in user_input
        ):
            st.session_state.grade = "2학년"

    st.session_state.messages.append(
        {
            "role": "user",
            "content": user_input
        }
    )

    with st.chat_message("user"):
        st.markdown(user_input)

    # =====================================================
    # 대학자료 검색
    # - 현재 질문을 최우선으로 검색
    # - 현재 질문만으로 공식자료를 찾지 못한 후속질문에만 최근 대화 활용
    # =====================================================

    current_rules = find_relevant_university_rules(user_input)
    current_scope = find_scope_matches(user_input)

    if current_rules:
        matched_rules = current_rules
        matched_scope = current_scope
    else:
        recent_user_text = "\n".join(
            m["content"]
            for m in st.session_state.messages[-8:]
            if m["role"] == "user"
        )
        matched_rules = find_relevant_university_rules(recent_user_text)
        matched_scope = find_scope_matches(recent_user_text)

    # =====================================================
    # 학교 교육과정
    # =====================================================

    if st.session_state.grade:
        curriculum = school_curriculum_text(
            st.session_state.grade
        )
    else:
        curriculum = (
            "아직 학생 학년이 확인되지 않았습니다. "
            "먼저 1학년/2학년을 확인해야 합니다."
        )

    university_evidence = university_evidence_text(
        matched_rules
    )

    scope_text = ""

    if matched_scope:
        scope_text = "\n".join(
            [
                f"- {r.get('대학', '')} / "
                f"{r.get('권역', '')} / "
                f"자료상태: {r.get('자료상태', '')}"
                for r in matched_scope
            ]
        )
    else:
        scope_text = "관련 전국대학 추적자료 없음"

    # =====================================================
    # 최근 대화만 모델에 전달
    # =====================================================

    history = st.session_state.messages[-12:]

    history_text = "\n\n".join(
        [
            (
                "학생: " + m["content"]
                if m["role"] == "user"
                else "상담AI: " + m["content"]
            )
            for m in history
        ]
    )

    # =====================================================
    # 모델에게 전달할 입력
    # =====================================================

    context = f"""
현재 학생 학년:
{st.session_state.grade or '미확인'}

적용 대입학년도:
{
    '2029학년도'
    if st.session_state.grade == '1학년'
    else '2028학년도'
    if st.session_state.grade == '2학년'
    else '미확인'
}

[서강고 해당 학생 교육과정]

{curriculum}

[질문과 관련하여 현재 구조화 DB에서 검색된 대학 공식자료]

{university_evidence}

[전국 대학 추적 DB]

{scope_text}

[최근 상담 대화]

{history_text}

[이번 학생 질문]

{user_input}
"""

    # =====================================================
    # OpenAI 호출
    # =====================================================

    with st.chat_message("assistant"):

        with st.spinner(
            "대학 공식자료와 서강고 교육과정을 확인하고 있습니다..."
        ):

            try:

                response = client.responses.create(
                    model=MODEL,
                    instructions=SYSTEM_INSTRUCTIONS,
                    input=context,
                    reasoning={
                        "effort": "medium"
                    },
                    max_output_tokens=1800,
                )

                answer = response.output_text

            except Exception as e:

                answer = (
                    "현재 AI 상담 서버 호출 중 오류가 발생했습니다.\n\n"
                    "잠시 후 다시 시도해주세요."
                )

                st.error(str(e))

        st.markdown(answer)

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer
        }
    )
