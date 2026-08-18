from pathlib import Path
import csv
import re
import streamlit as st

BASE = Path(__file__).parent
DATA = BASE / "data"

st.set_page_config(page_title="서강고 선택과목 상담", page_icon="🎓", layout="wide")

def load_csv(name):
    with open(DATA/name, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

rules = load_csv("university_rules.csv")
scope = load_csv("university_scope.csv")
status29 = load_csv("source_status_2029.csv")
school25 = load_csv("school_2025.csv")
school26 = load_csv("school_2026.csv")

ALIASES = {
    "연세대":"연세대학교","경희대":"경희대학교","서울대":"서울대학교","고려대":"고려대학교",
    "중앙대":"중앙대학교","이화여대":"이화여자대학교","성균관대":"성균관대학교",
    "서강대":"서강대학교","한양대":"한양대학교",
}

def norm(s):
    return re.sub(r"[^0-9a-zA-Z가-힣]", "", (s or "").lower())

def canonical_univ(name):
    return ALIASES.get(name, name)

def scope_universities():
    names = {r["대학"] for r in scope}
    names |= {r["대학"] for r in rules}
    return sorted(names)

def semester_rows(grade, term):
    data = school26 if grade=="1학년" else school25
    return [r for r in data if r["학기"] == term]

def terms_for_grade(grade):
    data = school26 if grade=="1학년" else school25
    seen=[]
    for r in data:
        if r["학기"] not in seen: seen.append(r["학기"])
    return seen

def rule_match(univs, major):
    q = norm(major)
    out=[]
    for r in rules:
        if canonical_univ(r["대학"]) not in {canonical_univ(x) for x in univs}: 
            continue
        target = norm(r["모집단위"])
        kws=[norm(x) for x in (r.get("검색키워드") or "").split("|") if x.strip()]
        if q and (q in target or target in q or any(k and (k in q or q in k) for k in kws)):
            out.append(r)
    return out

def split_courses(text):
    if not text: return []
    # Keep "A 또는 B" as human-readable; split only pipe-separated fields.
    return [x.strip() for x in text.split("|") if x.strip()]

def collect_official_courses(matches):
    courses=[]
    for r in matches:
        courses += split_courses(r.get("핵심과목",""))
        courses += split_courses(r.get("권장과목",""))
    # phrases containing OR are not exact selectable course names
    exact=[]
    for c in courses:
        if " 또는 " in c or " 중 " in c or "·" in c:
            continue
        exact.append(c)
    return list(dict.fromkeys(exact))

def validate_term(rows, selected, prior_selected):
    maxn = int(rows[0]["선택수"]) if rows else 0
    course_map={r["과목명"]:r for r in rows}
    errors=[]; warnings=[]
    if len(selected) != maxn:
        errors.append(f"이 학기는 정확히 {maxn}과목을 선택해야 합니다. 현재 {len(selected)}과목입니다.")
    mand=[c for c in selected if course_map.get(c,{}).get("의무교과군")=="Y"]
    if len(mand) != 1:
        errors.append(f"정보·제2외국어·한문 교과군은 정확히 1과목이어야 합니다. 현재 {len(mand)}과목입니다.")
    dup=sorted(set(selected) & set(prior_selected))
    if dup:
        errors.append("이미 앞 학기에 선택한 동일 과목을 다시 선택했습니다: " + ", ".join(dup))
    return errors,warnings

st.title("🎓 서강고 선택과목 상담")
st.caption("서강고 교육과정과 검증된 대학 공식 권장과목 DB를 바탕으로 과목 선택을 점검하는 무료 상담 도구입니다.")

with st.container(border=True):
    st.markdown("### 1. 학생 정보")
    grade = st.radio("현재 학년", ["1학년","2학년"], horizontal=True)
    target_year = "2029" if grade=="1학년" else "2028"
    st.info(f"{grade} 학생은 **{target_year}학년도 대입** 기준으로 상담합니다.")
    if grade=="1학년":
        st.warning("2029 대학별 세부자료가 아직 미공개인 경우, 2028 공식자료는 참고용으로만 표시합니다.")

    univs = st.multiselect("관심 대학", scope_universities(), placeholder="대학을 검색해서 선택하세요")
    major = st.text_input("희망 학과·전공", placeholder="예: 전기전자공학부, 간호학과, 컴퓨터공학")

st.markdown("### 2. 대학 공식자료 대조")
matches = rule_match(univs, major) if univs and major.strip() else []
if not univs or not major.strip():
    st.caption("관심 대학과 희망 전공을 입력하면 현재 구조화된 공식자료와 대조합니다.")
elif matches:
    for r in matches:
        with st.container(border=True):
            st.markdown(f"**{r['대학']} · {r['모집단위']}**")
            if r.get("핵심과목"):
                st.write("핵심과목:", ", ".join(split_courses(r["핵심과목"])))
            if r.get("권장과목"):
                st.write("권장과목:", ", ".join(split_courses(r["권장과목"])))
            if r.get("추가조건"):
                st.caption(r["추가조건"])
            if target_year=="2029":
                st.warning("2028 공식자료 참고 / 2029 미확정")
            else:
                st.success("2028학년도 공식자료 적용")
            if r.get("출처URL"):
                st.markdown(f"[공식 출처 열기]({r['출처URL']})")
else:
    st.warning("선택한 대학·전공의 세부 규칙이 현재 구조화 DB에 없습니다. 이 도구는 없는 정보를 추정하지 않습니다.")
    st.caption("전국 대학은 추적 대상이지만, 세부 전공별 공식표가 아직 구조화되지 않은 대학이 있습니다.")

official_courses = collect_official_courses(matches)

st.markdown("### 3. 학기별 과목 조합 만들기")
st.caption("각 학기 선택 규칙을 실시간으로 검증합니다. 동일 과목은 다른 학기에 다시 선택할 수 없습니다.")

all_previous=[]
term_selections={}
for term in terms_for_grade(grade):
    rows=semester_rows(grade,term)
    names=[r["과목명"] for r in rows]
    default=[]
    # Soft school recommendations for grade 3
    for c in ["화법과 언어","확률과 통계"]:
        if c in names and c not in all_previous:
            default.append(c)
    # Add exact official recommended courses if available in this term
    for c in official_courses:
        if c in names and c not in default and c not in all_previous:
            default.append(c)
    # Keep defaults under capacity, reserve one mandatory slot
    maxn=int(rows[0]["선택수"])
    default=[c for c in default if next((x for x in rows if x["과목명"]==c),{}).get("의무교과군")!="Y"][:max(0,maxn-1)]

    with st.expander(term, expanded=True):
        st.write(f"**{maxn}과목 선택** · 정보/제2외국어/한문 교과군 **정확히 1과목 필수**")
        selected=st.multiselect(
            f"{term} 선택과목",
            names,
            default=default,
            key=f"sel_{grade}_{term}"
        )
        term_selections[term]=selected
        errors,_=validate_term(rows,selected,all_previous)
        if errors:
            for e in errors: st.error(e)
        else:
            st.success("학교 선택 규칙을 충족합니다.")
        # Explain mandatory group
        mandatory=[r["과목명"] for r in rows if r["의무교과군"]=="Y"]
        st.caption("이 학기 의무 교과군 선택지: " + ", ".join(mandatory))
        if "3학년" in term:
            recs=[c for c in ["화법과 언어","확률과 통계"] if c in names]
            if recs:
                st.caption("학교 권장: " + ", ".join(recs) + " (강제조건 아님)")
    all_previous += selected

st.markdown("### 4. 종합 점검")
all_errors=[]
previous=[]
for term,selected in term_selections.items():
    rows=semester_rows(grade,term)
    errs,_=validate_term(rows,selected,previous)
    all_errors += [f"{term}: {e}" for e in errs]
    previous += selected

if all_errors:
    st.error("아직 수정이 필요한 항목이 있습니다.")
    for e in all_errors:
        st.write("- " + e)
else:
    st.success("현재 입력한 과목 조합은 서강고 선택 규칙을 모두 충족합니다.")

if matches:
    selected_all=set(sum(term_selections.values(),[]))
    exact=set(official_courses)
    covered=sorted(exact & selected_all)
    missing=sorted(exact - selected_all)
    if covered:
        st.write("**현재 조합에서 확인되는 대학 공식 연계 과목:** " + ", ".join(covered))
    if missing:
        st.info("**공식자료상 추가 검토할 과목:** " + ", ".join(missing))
        st.caption("미이수=지원 불가라는 뜻이 아닙니다. 대학의 '권장'과 '필수'를 구분해 확인하세요.")

st.divider()
with st.expander("자료의 범위와 한계"):
    st.write(
        "이 무료 버전은 규칙 기반 도구입니다. 대학 공식자료가 구조화된 범위에서만 대학별 대조를 하며, "
        "DB에 없는 내용을 AI처럼 추정하지 않습니다. 현재 상세 규칙 DB는 검증 완료된 대학/전공부터 순차적으로 확대하는 구조입니다."
    )
    st.write("1학년(2029 대입)은 2029 공식자료가 확인되면 그 자료가 2028 참고자료보다 우선해야 합니다.")
    st.write("최종 과목 선택 전 담임교사 또는 교육과정 담당교사와 확인하세요.")

st.caption("개인정보를 저장하지 않습니다. 이름·학번·연락처 입력은 필요하지 않습니다.")
