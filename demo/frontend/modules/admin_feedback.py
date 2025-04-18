import os
import subprocess

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# 한글 폰트 설정
font_path = "/usr/share/fonts/truetype/nanum/NanumMyeongjo.ttf"
fontprop = fm.FontProperties(fname=font_path, size=10)
plt.rc("font", family=fontprop.get_name())

API_BASE_URL = "http://localhost:5000/api"


def admin_view_feedback():
    st.write("## 📑 리뷰 결과 분석")

    r = requests.get(f"{API_BASE_URL}/users")
    if r.status_code == 200 and r.json().get("success"):
        all_users = r.json()["users"]
        filtered_users = [u for u in all_users if u["role"] == "user"]
        if not filtered_users:
            st.info("일반 사용자 계정이 없습니다.")
            return
        # 그룹 정보를 먼저 조회
        group_response = requests.get(f"{API_BASE_URL}/groups")
        if group_response.status_code == 200 and group_response.json().get("success"):
            groups = {g["id"]: g for g in group_response.json()["groups"]}
        else:
            st.error("그룹 정보를 불러오는 데 실패했습니다.")
            return

        # 이름과 그룹명을 함께 표시하도록 수정
        name_map = {}
        for u in filtered_users:
            group_name = groups.get(u.get("group_id"), {"group_name": "미지정"})[
                "group_name"
            ]
            display_name = f"{u['name']} ({group_name})"
            name_map[display_name] = u["username"]

        feedback_matrix = []
        completed_users = []
        in_progress_users = []
        incomplete_users = []

        group_completion = {}  # 그룹별 완료 상태 저장

        for from_user in filtered_users:
            row = []
            for to_user in filtered_users:
                if from_user["username"] == to_user["username"]:
                    row.append(None)
                else:
                    response = requests.get(
                        f"{API_BASE_URL}/feedback/check",
                        params={
                            "from_username": from_user["username"],
                            "to_username": to_user["username"],
                        },
                    )
                    if response.status_code == 200 and response.json().get("success"):
                        row.append(1 if response.json().get("already_submitted") else 0)
                    else:
                        row.append(0)
            feedback_matrix.append(row)

        df_status = pd.DataFrame(
            feedback_matrix,
            columns=[
                f"{u['name']} ({groups.get(u.get('group_id'), {'group_name': '미지정'})['group_name']})"
                for u in filtered_users
            ],
            index=[
                f"{u['name']} ({groups.get(u.get('group_id'), {'group_name': '미지정'})['group_name']})"
                for u in filtered_users
            ],
        )

        for user in filtered_users:
            user_group_id = user.get("group_id")
            display_name = f"{user['name']} ({groups.get(user_group_id, {'group_name': '미지정'})['group_name']})"
            if user_group_id:
                group_users = [
                    u for u in filtered_users if u.get("group_id") == user_group_id
                ]
                feedbacks = df_status.loc[
                    display_name,
                    [
                        f"{u['name']} ({groups.get(u.get('group_id'), {'group_name': '미지정'})['group_name']})"
                        for u in group_users
                    ],
                ].dropna()
                feedback_count = feedbacks.sum()  # 1인 값의 개수
                total_members = len(feedbacks)  # 그룹 내 멤버 수
                if feedback_count == total_members:  # 모든 사람이 완료
                    completed_users.append(display_name)
                elif feedback_count > 0:  # 최소 1명이라도 완료한 경우 (일부만 완료됨)
                    in_progress_users.append(display_name)
                else:  # 아무도 완료하지 않은 경우
                    incomplete_users.append(display_name)
            else:
                incomplete_users.append(display_name)

        # 그룹별 완료 상태 저장
        for group_id, group_info in groups.items():
            group_users = [u for u in filtered_users if u.get("group_id") == group_id]
            if len(group_users) <= 1:  # 그룹 내 사용자가 1명 이하면 완료로 처리
                group_completion[group_id] = {
                    "group_name": group_info,
                    "status": "완료",
                }
                continue

            all_completed = True
            for from_user in group_users:
                for to_user in group_users:
                    if from_user["username"] != to_user["username"]:
                        response = requests.get(
                            f"{API_BASE_URL}/feedback/check",
                            params={
                                "from_username": from_user["username"],
                                "to_username": to_user["username"],
                            },
                        )
                        if not (
                            response.status_code == 200
                            and response.json().get("success")
                            and response.json().get("already_submitted")
                        ):
                            all_completed = False
                            break
                if not all_completed:
                    break

            if all_completed:
                group_completion[group_id] = {
                    "group_name": group_info,
                    "status": "완료",
                }
            else:
                # 진행 상태 확인
                any_completed = False
                for from_user in group_users:
                    for to_user in group_users:
                        if from_user["username"] != to_user["username"]:
                            response = requests.get(
                                f"{API_BASE_URL}/feedback/check",
                                params={
                                    "from_username": from_user["username"],
                                    "to_username": to_user["username"],
                                },
                            )
                            if (
                                response.status_code == 200
                                and response.json().get("success")
                                and response.json().get("already_submitted")
                            ):
                                any_completed = True
                                break
                    if any_completed:
                        break

                status = "진행중" if any_completed else "미완료"
                group_completion[group_id] = {
                    "group_name": group_info,
                    "status": status,
                }

        labels = ["완료", "진행중", "미완료"]
        values = [len(completed_users), len(in_progress_users), len(incomplete_users)]
        hover_text = [
            (
                f"피드백 완료 사용자:<br>" + "<br>".join(completed_users)
                if completed_users
                else "피드백 완료 사용자: 없음"
            ),
            (
                f"피드백 진행중 사용자:<br>" + "<br>".join(in_progress_users)
                if in_progress_users
                else "피드백 진행중 사용자: 없음"
            ),
            (
                f"피드백 미완료 사용자:<br>" + "<br>".join(incomplete_users)
                if incomplete_users
                else "피드백 미완료 사용자: 없음"
            ),
        ]

        fig_user = go.Figure(
            data=[
                go.Pie(
                    labels=labels,
                    values=values,
                    hole=0.5,
                    hoverinfo="label+percent",
                    textinfo="value",
                    hovertext=hover_text,
                    hovertemplate="%{hovertext}<extra></extra>",
                )
            ]
        )
        fig_user.update_traces(
            marker=dict(colors=["#08c7b4", "#ffcc99", "#ff9999"])
        )  # 색상 변경
        fig_user.update_layout(title="피드백 완료 현황")

        group_counts = {"완료": 0, "진행중": 0, "미완료": 0}
        group_hover_text = {"완료": [], "진행중": [], "미완료": []}
        for group_id, info in group_completion.items():
            group_counts[info["status"]] += 1
            group_hover_text[info["status"]].append(info["group_name"]["group_name"])

        fig_group = go.Figure(
            data=[
                go.Pie(
                    labels=list(group_counts.keys()),
                    values=list(group_counts.values()),
                    hole=0.5,
                    textinfo="value",
                    hoverinfo="label+percent",
                    hovertext=[
                        f"{status}:<br>" + "<br>".join(names)
                        for status, names in group_hover_text.items()
                    ],
                    hovertemplate="%{hovertext}<extra></extra>",
                )
            ]
        )
        fig_group.update_traces(
            marker=dict(colors=["#08c7b4", "#ffcc99", "#ff9999"])
        )  # 색상 변경
        fig_group.update_layout(title="그룹별 피드백 완료 현황")

        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(fig_user)
        with col2:
            st.plotly_chart(fig_group)

        # PDF 생성 제어 상태 초기화
        if "pdf_generated" not in st.session_state:
            st.session_state.pdf_generated = False

        # PDF 생성 버튼
        if not st.session_state.pdf_generated:
            if st.button("PDF 생성 시작"):
                backend_dir = os.path.join(os.path.dirname(__file__), "../../backend")
                with st.status("PDF 생성 중..."):
                    try:
                        env = os.environ.copy()
                        env["PYTHONPATH"] = backend_dir
                        subprocess.run(
                            ["python", os.path.join(backend_dir, "db/models/pdf.py")],
                            check=True,
                            env=env,
                        )
                        subprocess.run(
                            [
                                "python",
                                os.path.join(backend_dir, "build_pdf/make_pdf.py"),
                            ],
                            check=True,
                            env=env,
                        )
                        st.session_state.pdf_generated = True
                        st.success("PDF 생성이 완료되었습니다.")
                    except subprocess.CalledProcessError as e:
                        st.error(f"PDF 생성 중 오류 발생!\n\n{e}")  # 오류 메시지 출력

        # PDF가 생성된 경우에만 결과 조회 옵션 표시
        if st.session_state.pdf_generated:
            sel_name = st.selectbox("조회할 사용자 이름", list(name_map.keys()))
            sel_username = name_map[sel_name]

            if st.button("결과 조회"):
                params = {"username": sel_username}
                fb = requests.get(f"{API_BASE_URL}/feedback/user", params=params)
                if fb.status_code == 200:
                    data = fb.json()
                    if data.get("success"):
                        feedbacks = data["feedbacks"]
                        if feedbacks:
                            # 결과 요약 페이지 호출
                            pdf_url = f"{API_BASE_URL}/summary/{sel_username}"
                            pdf_display = f"""<iframe src="{pdf_url}" width="800" height="1200" style="border: none;"></iframe>"""
                            st.markdown(pdf_display, unsafe_allow_html=True)
                        else:
                            st.info("해당 사용자가 받은 피드백이 없습니다.")
                    else:
                        st.error("피드백 조회 실패: " + data.get("message", ""))
                else:
                    st.error("피드백 조회 API 오류")
        else:
            st.info("PDF를 생성한 후에 결과를 조회할 수 있습니다.")
