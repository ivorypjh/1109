from datetime import datetime
from pathlib import Path
import pandas as pd
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

# DAG 정의
# start_date 와 schedule_interval 은 필수 요소
dag = DAG(
    dag_id="NoCatchUp", # dag 이름
    start_date=datetime(2023, 11, 1), # 시작 날짜
    schedule_interval="@daily", # 매일 수행하기,
    catchup=False # catchup 설정
    #schedule_interval=None # 간격을 설정하지 않는 경우 None 으로 설정, 1번만 수행됨
)
# schedule_interval="@daily" - 매일 수행하기

# 작업 생성
# 웹 API 다운로드는 Bash 와 Python 모두 가능함
# bash 오퍼레이터를 사용하는 것 보다는 파이썬 오퍼레이터를 사용하는게 좋음
# bash 에서 echo 를 사용하면 보이지 않지만 파이썬에서 print 를 사용하면 로그에서 확인이 가능하며
# 프로그래밍 언어를 사용하기 때문에 예외 처리가 가능
fetch_events = BashOperator( # bash 를 사용해서 다운로드
    task_id="fetch_date",
    bash_command=(
        # curl -o 데이터를저장할위치 요청할경로
        # 요청할 경로는 자신의 로컬 주소를 사용
        "curl -o /tmp/{{ds}}.json  http://43.201.58.54:5000/events?" # ds 를 사용해서 현재 실행 날짜를 적용
				"start_date={{execution_date.strftime('%Y-%m-%d')}}&"
				"end_date={{next_execution_date.strftime('%Y-%m-%d')}}"
    ),
    dag=dag,
)

# 파이썬 작업
#def _calculate_stats(input_path, output_path): - 기존의 코드
# 함수의 매개별수를 ** 로 만들면 모든 매개변수를 dict로 받아들임
# airflow 에서는 PythonOperator 가 생성한 모든 데이터와 기본적으로 사용할 수 있는
# 모든 매개변수를 한꺼번에 받아옴
# 매개변수 이름은 어떤 것을 사용해도 상관없지만 
# 관습적으로 데이터를 저장한다는 의미로 context 로 설정하는 경우가 많음
# context 라는 것은 여러 곳에서 공유해서 사용할 수 있는 저장소를 의미
def _calculate_stats(**context):
    # dict 형태로 받아오므로 key 형식을 사용해서 path 를 설정
    input_path = context["templates_dict"]["input_path"]
    output_path = context["templates_dict"]["output_path"]
    # 경로를 생성
    Path(output_path).parent.mkdir(exist_ok=True)
    # json 파싱 - 위에서 설정한 경로를 사용해서 파싱
    events = pd.read_json(input_path)
    # 이후 원하는 작업 수행 

    # 연산 수행 - 그룹 별로 묶은 다음 사이즈(크기)를 구하고 인덱스를 리셋
    stats = events.groupby(["date", "user"]).size().reset_index()
    # 저장
    stats.to_csv(output_path, index=False)

# 파이썬 오퍼레이터 생성
calculate_stats = PythonOperator(
    # 오퍼레이터는 항상 먼저 태스크 아이디를 생성
    task_id="calculate_stats",
    # python_callable 에는 함수 이름을 사용
    python_callable=_calculate_stats,
    # 파라미터 전달 - dict 형태 사용
    #op_kwargs={"input_path": "/tmp/events.json",
    #           "output_path": "/tmp/stats.csv"},
    
    # 위에서 ds 변수를 사용하도록 수정했기 때문에 
    # 여기도 이를 반영하도록 파일 경로를 수정
    # 이렇게 해야 증분 처리가 가능
    templates_dict={
        "input_path":"/tmp/{{ds}}.json",
        "output_path":"/tmp/{{ds}}.csv"
    },
    dag=dag,
)

# 작업할 순서를 지정
# 데이터를 가져와서 연산을 수행하고 파라미터를 전달
fetch_events >> calculate_stats