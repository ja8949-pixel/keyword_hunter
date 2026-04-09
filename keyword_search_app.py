"""
키워드 즉석 분석 + 황금키워드 자동 발굴 웹앱
"""
import os, requests, json, time, hmac, hashlib, base64, threading
from datetime import datetime
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from flask import Flask, request, jsonify, render_template_string

# ═══════════════════════════════════════════
# API 키
# ═══════════════════════════════════════════
NAVER_CLIENT_ID     = "9WP1sJzH_TeClyNlFIZp"
NAVER_CLIENT_SECRET = "0GyVTdydcg"
AD_API_KEY     = "010000000071c4713a54aff3d2dbda31c2a9ffddc936d1014c1997acfd761f664737b04264"
AD_SECRET_KEY  = "AQAAAABxxHE6VK/z0tvaMcKp/93JyVVQQOKvNTSZK7ByhbQVEA=="
AD_CUSTOMER_ID = "4026650"

GOLD_MAX_DOCS  = 3000
HISTORY_FILE   = "keyword_history.json"

app = Flask(__name__)

# ═══════════════════════════════════════════
# 커넥션 풀 세션 (속도 최적화)
# ═══════════════════════════════════════════
blog_session = requests.Session()
blog_session.headers.update({
    "X-Naver-Client-Id":     NAVER_CLIENT_ID,
    "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
})
blog_session.mount("https://", HTTPAdapter(pool_connections=30, pool_maxsize=30))

ad_session = requests.Session()
ad_session.mount("https://", HTTPAdapter(pool_connections=10, pool_maxsize=10))

# ═══════════════════════════════════════════
# 자동 발굴 상태
# ═══════════════════════════════════════════
scan_state = {"running": False, "progress": 0, "total": 0,
              "checked": 0, "found": 0, "phase": "", "results": [], "log": []}
scan_lock  = threading.Lock()

# ═══════════════════════════════════════════
# 30개 주제별 시드 키워드
# ═══════════════════════════════════════════
TOPICS = {
    "korean_food":   {"label": "🍳 한식 레시피", "seeds": [
        "한식레시피","집밥만들기","찌개레시피","반찬만들기","볶음요리","조림요리","국물요리","무침레시피",
        "된장찌개만들기","김치찌개레시피","순두부찌개","갈비찜레시피","불고기만들기","제육볶음","잡채만들기",
        "떡볶이만들기","비빔밥레시피","삼겹살요리","닭볶음탕","된장국레시피","미역국만들기","콩나물국",
        "도시락반찬","간단반찬","밑반찬만들기","나물무침","김치만들기","에어프라이어한식","솥밥레시피",
    ]},
    "world_food":    {"label": "🍝 양식·중식·일식", "seeds": [
        "파스타만들기","크림파스타","오일파스타","까르보나라","리조또레시피","피자만들기","스테이크굽기",
        "짜장면만들기","짬뽕만들기","마파두부","깐풍기","탕수육만들기","마라탕만들기","중국식볶음밥",
        "라멘만들기","우동레시피","돈카츠","오야코동","데리야끼","일본카레","규동만들기","차슈만들기",
        "팟타이만들기","쌀국수만들기","월남쌈","타코만들기","부리또","인도카레만들기","훠궈집에서",
    ]},
    "diet_food":     {"label": "🥗 다이어트 식단", "seeds": [
        "다이어트식단","저칼로리요리","다이어트도시락","간헐적단식식단","키토식단","저탄고지식단",
        "닭가슴살요리","두부다이어트","샐러드만들기","단백질식단","체중감량식단","1200칼로리식단",
        "다이어트간식","포만감식품","클린이팅","다이어트볶음밥","저당식단","당뇨식단","저염식단",
        "다이어트죽","디톡스주스","귀리요리","퀴노아샐러드","고구마다이어트","두부스테이크",
    ]},
    "baking":        {"label": "🍰 베이킹 / 디저트", "seeds": [
        "케이크만들기","쿠키만들기","빵만들기","마카롱만들기","타르트만들기","치즈케이크","롤케이크",
        "파운드케이크","브라우니만들기","머핀만들기","스콘만들기","도넛만들기","크로플만들기",
        "마들렌만들기","와플만들기","팬케이크만들기","식빵만들기","소금빵만들기","시나몬롤",
        "크루아상만들기","베이글만들기","홈베이킹초보","에어프라이어베이킹","글루텐프리빵",
    ]},
    "cafe_drinks":   {"label": "☕ 홈카페 / 음료", "seeds": [
        "홈카페음료","달고나커피만들기","아이스커피만들기","라떼만들기","에이드만들기","스무디만들기",
        "버블티만들기","과일청만들기","레몬에이드","자몽에이드","딸기라떼만들기","말차라떼",
        "콜드브루만들기","드립커피","홈카페레시피","수제청만들기","레몬청만들기","생강청만들기",
        "논알콜칵테일","목테일만들기","오트밀크라떼","홈카페도구추천","커피머신추천",
    ]},
    "fitness":       {"label": "💪 헬스 / 홈트레이닝", "seeds": [
        "헬스초보운동","헬스루틴","스쿼트자세","데드리프트","벤치프레스","풀업방법","런지운동",
        "홈트운동","맨몸운동루틴","덤벨운동","코어운동","복근운동","하체운동","어깨운동",
        "유산소운동효과","인터벌트레이닝","체지방감소운동","근육증가운동","운동전후식단",
        "프로틴추천","크레아틴효과","운동복추천","헬스장선택방법","PT가격",
    ]},
    "yoga":          {"label": "🧘 요가 / 필라테스", "seeds": [
        "요가초보","요가자세","다이어트요가","허리통증요가","골반교정요가","요가루틴","빈야사요가",
        "필라테스효과","필라테스초보","매트필라테스","기구필라테스","필라테스다이어트",
        "스트레칭방법","전신스트레칭","기상스트레칭","폼롤러사용법","근막이완","고관절스트레칭",
        "명상방법","마음챙김","호흡법","복식호흡","명상앱추천","필라테스자격증",
    ]},
    "health":        {"label": "🏥 건강 / 질환 정보", "seeds": [
        "건강검진항목","혈액검사수치","고혈압관리","당뇨관리","고지혈증치료","갑상선질환","빈혈증상",
        "역류성식도염","과민성대장증후군","변비해결","장염증상","위염치료","허리디스크증상",
        "무릎관절염","오십견치료","두통원인","편두통치료","어지럼증원인","피부염증상","아토피관리",
        "수면무호흡","불면증원인","피로만성원인","면역력높이는법","항산화식품","뇌건강음식",
    ]},
    "supplements":   {"label": "💊 영양제 / 건강식품", "seeds": [
        "종합비타민추천","비타민C효능","비타민D효능","마그네슘효능","아연효능","오메가3추천",
        "루테인효능","콜라겐효능","유산균추천","프로바이오틱스효능","철분제추천","칼슘마그네슘",
        "밀크씨슬효능","강황효능","홍삼효능","글루코사민추천","보스웰리아효능",
        "다이어트영양제","카르니틴효능","임산부영양제","어린이영양제","피부영양제","탈모영양제",
        "영양제복용순서","영양제공복섭취","영양제조합","영양제브랜드추천",
    ]},
    "skincare":      {"label": "✨ 스킨케어", "seeds": [
        "스킨케어루틴","기초화장품순서","건성피부관리","지성피부관리","민감성피부케어","모공관리방법",
        "토너추천","에센스추천","세럼추천","앰플추천","수분크림추천","선크림추천","미백에센스",
        "주름크림추천","아이크림추천","클렌징폼추천","클렌징오일추천","마스크팩추천","수분팩",
        "레티놀효능","나이아신아마이드","히알루론산크림","피부장벽강화","각질케어방법",
        "여드름케어","여드름흉터관리","색소침착개선","블랙헤드제거",
    ]},
    "makeup":        {"label": "💄 메이크업 / 네일", "seeds": [
        "메이크업순서","데일리메이크업","파운데이션추천","쿠션팩트추천","컨실러추천","파우더추천",
        "아이섀도우추천","아이라이너추천","마스카라추천","립스틱추천","립틴트추천","립글로스추천",
        "블러셔추천","하이라이터추천","컨투어링방법","눈썹그리기","눈썹펜추천",
        "셀프네일아트","네일폴리시추천","젤네일추천","네일스티커추천",
        "봄메이크업","여름메이크업","직장인메이크업","웨딩메이크업",
    ]},
    "fashion_w":     {"label": "👗 여성 패션 / 코디", "seeds": [
        "여성코디추천","데일리룩여성","오피스룩여성","봄여성코디","여름여성코디","가을여성코디","겨울여성코디",
        "원피스코디","슬랙스코디","청바지코디여성","스커트코디","블라우스코디","니트코디여성",
        "코트코디여성","패딩코디여성","키작은여성코디","통통체형코디",
        "여성신발추천","스니커즈여성추천","힐추천","부츠추천",
        "여성가방추천","크로스백추천","토트백추천","주얼리추천","귀걸이추천",
    ]},
    "fashion_m":     {"label": "👔 남성 패션 / 코디", "seeds": [
        "남성코디추천","남자데일리룩","남자오피스룩","봄남성코디","여름남성코디","가을남성코디","겨울남성코디",
        "남자청바지코디","남자슬랙스코디","남자티셔츠코디","남자셔츠코디","남자니트코디",
        "남자코트코디","남자패딩추천","남자스니커즈추천","나이키추천","아디다스추천","뉴발란스추천",
        "남자가방추천","백팩추천남자","남성스킨케어루틴","남자선크림추천","남자머리스타일",
    ]},
    "hair":          {"label": "💇 헤어스타일 / 케어", "seeds": [
        "여자헤어스타일","남자헤어스타일","단발머리","중단발머리","레이어드컷","울프컷","리프컷",
        "셀프염색방법","탈색방법","새치염색","뿌리염색","파마추천","볼륨펌","스트레이트펌",
        "헤어케어루틴","두피케어방법","지성두피관리","탈모예방방법","탈모샴푸추천","두피영양제",
        "샴푸추천","트리트먼트추천","헤어마스크추천","헤어오일추천","헤어드라이기추천","고데기추천",
    ]},
    "pregnancy":     {"label": "🤰 임신 / 출산", "seeds": [
        "임신초기증상","임신준비방법","임신중금지음식","임신중좋은음식","임산부영양제","임신중운동",
        "태교방법","태교음악","태교여행추천","분만방법","자연분만","제왕절개회복","출산준비물",
        "산후조리원추천","산후도우미","산후다이어트","산후우울증","출산후탈모",
        "모유수유방법","모유량늘리는법","젖몸살해결","신생아용품준비","유모차추천","카시트추천",
    ]},
    "baby":          {"label": "🍼 영아 육아 (0~36개월)", "seeds": [
        "신생아돌봄","신생아수면","신생아목욕","아기수유간격","분유추천","혼합수유방법",
        "아기잠재우기","퇴행수면해결","아기수면교육","3개월아기발달","6개월아기발달","12개월아기발달",
        "이유식시작시기","초기이유식만들기","중기이유식","후기이유식","아기간식추천",
        "아기피부트러블","기저귀발진치료","아기발달장난감","애착인형추천","아기띠추천","아기용품쇼핑몰",
    ]},
    "kids_edu":      {"label": "🧒 유아 교육 / 아동", "seeds": [
        "유아발달","5살아이발달","7살초등준비","유아교육방법","언어발달자극","인지발달놀이",
        "어린이집적응방법","유치원준비물","아이훈육방법","올바른훈육","아이감정코칭",
        "독서교육방법","그림책추천","어린이책추천","한글공부방법","영어공부유아",
        "장난감추천","레고추천연령별","어린이영양제","아이편식고치기","키즈카페","실내놀이아이",
    ]},
    "dom_travel":    {"label": "🗺️ 국내 여행 코스", "seeds": [
        "국내여행추천","당일치기여행","1박2일코스","2박3일여행","혼자국내여행","커플국내여행","가족여행국내",
        "제주여행코스","부산여행코스","경주여행코스","강릉여행코스","여수여행코스","속초여행코스",
        "전주여행코스","통영여행","남해여행","거제여행코스","춘천여행","가평여행코스",
        "양양여행","강화도여행","서울근교여행","드라이브코스","단풍여행","벚꽃명소여행",
    ]},
    "ovs_travel":    {"label": "🌏 해외 여행", "seeds": [
        "일본여행코스","오사카여행","도쿄여행코스","교토여행","후쿠오카여행","오키나와여행","홋카이도여행",
        "태국여행코스","방콕여행","치앙마이여행","푸켓여행",
        "베트남여행","다낭여행코스","호이안여행","하노이여행","호치민여행",
        "발리여행코스","싱가포르여행","홍콩여행","대만여행코스",
        "유럽여행코스","파리여행","로마여행","미국여행코스","하와이여행코스","괌여행코스",
    ]},
    "restaurant":    {"label": "🍽️ 맛집 탐방", "seeds": [
        "서울맛집추천","홍대맛집","강남맛집","성수동맛집","이태원맛집","건대맛집","종로맛집",
        "부산맛집추천","해운대맛집","서면맛집","광안리맛집",
        "제주맛집추천","강릉맛집추천","속초맛집","경주맛집","전주맛집추천",
        "혼밥맛집","데이트맛집","분위기좋은식당","가족맛집","가성비식당",
        "고기집추천","초밥맛집","라멘맛집","줄서는맛집","숨은맛집",
    ]},
    "cafe":          {"label": "☕ 카페 / 디저트 투어", "seeds": [
        "분위기좋은카페","감성카페추천","인스타카페","루프탑카페",
        "서울카페추천","홍대카페","성수카페","연남동카페","익선동카페","망원동카페",
        "부산카페추천","해운대카페","전주카페","제주카페추천","강릉카페","속초카페추천",
        "독특한카페","책카페추천","애견카페추천","크로플맛집","케이크맛집","마카롱맛집",
        "빵집추천","소금빵맛집","크루아상맛집","빙수맛집","디저트맛집추천",
    ]},
    "accommodation": {"label": "🏨 숙소 / 펜션 / 호텔", "seeds": [
        "펜션추천","풀빌라추천","글램핑추천","커플펜션","가족펜션추천","독채펜션추천",
        "제주숙소추천","부산호텔추천","강릉펜션추천","속초숙소추천","여수숙소추천","가평펜션추천",
        "오션뷰숙소","오션뷰호텔","한옥스테이","감성숙소추천",
        "서울호텔추천","5성급호텔","가성비호텔","조식포함호텔","리조트추천",
        "반려동물펜션","수영장펜션","바베큐펜션","온천숙소",
    ]},
    "stock":         {"label": "📈 주식 / ETF / 투자", "seeds": [
        "주식투자초보","주식공부방법","주식용어정리","재무제표보는법",
        "ETF투자방법","ETF추천","국내ETF","해외ETF","배당ETF","미국주식투자","S&P500투자",
        "배당주투자","배당주추천","가치투자방법","성장주투자",
        "HTS사용법","주식매매전략","분할매수방법","손절매방법",
        "코인투자방법","비트코인투자","금투자방법","리츠투자","ISA계좌","연금저축펀드",
    ]},
    "realestate":    {"label": "🏠 부동산 / 청약", "seeds": [
        "아파트청약방법","청약통장만들기","청약가점계산","특별공급청약","생애최초청약",
        "아파트시세조회","아파트매매방법","전세계약방법","월세계약","전세사기예방",
        "확정일자받기","전입신고방법","주택담보대출","전세자금대출","LTV계산",
        "재개발투자","재건축아파트","임대사업자등록","월세수익률","수익형부동산",
        "원룸구하는법","오피스텔투자","호갱노노활용","네이버부동산활용",
    ]},
    "saving":        {"label": "💳 절약 / 가계부 / 재테크", "seeds": [
        "절약방법","생활비절약","식비절약","공과금절약","가계부쓰는법","가계부앱추천",
        "짠테크방법","무지출챌린지","소비다이어트","충동구매막기",
        "신용카드추천","체크카드추천","캐시백카드추천","카드포인트활용","연회비없는카드",
        "통신비절약","알뜰폰추천","연말정산공제","소득공제방법","정부지원금","청년혜택",
        "부업추천","투잡방법","온라인부업","블로그수익","스마트스토어창업",
    ]},
    "laptop":        {"label": "💻 노트북 / PC / 가전", "seeds": [
        "노트북추천","맥북추천","LG그램추천","갤럭시북추천","학생노트북추천","게임노트북추천",
        "데스크탑PC추천","게이밍PC추천","모니터추천","4K모니터추천","게임모니터추천",
        "키보드추천","기계식키보드","무선키보드추천","무선마우스추천",
        "이어폰추천","무선이어폰추천","노이즈캔슬링이어폰",
        "냉장고추천","세탁기추천","건조기추천","식기세척기추천",
        "공기청정기추천","청소기추천","로봇청소기추천","에어프라이어추천",
    ]},
    "smartphone":    {"label": "📱 스마트폰 / 앱 / IT", "seeds": [
        "아이폰추천","갤럭시추천","스마트폰비교","가성비폰추천","중고폰구매",
        "아이패드추천","갤럭시탭추천","태블릿추천",
        "생산성앱추천","일정관리앱","메모앱추천","사진편집앱추천","영상편집앱추천",
        "챗GPT활용법","AI앱추천","생성AI도구","업무자동화",
        "유튜브알고리즘","유튜브수익화방법","인스타그램팔로워늘리기",
        "블로그운영방법","네이버블로그수익","티스토리운영","쿠팡마켓",
    ]},
    "dog":           {"label": "🐶 강아지", "seeds": [
        "강아지입양방법","강아지분양","소형견추천","강아지품종추천",
        "강아지기초훈련","강아지배변훈련방법","강아지짖음훈련","강아지사회화방법",
        "강아지사료추천","강아지간식추천","강아지수제간식",
        "강아지건강검진","강아지예방접종스케줄","강아지중성화","강아지피부병","강아지눈물자국",
        "강아지목욕방법","강아지미용비용","강아지용품추천","강아지하네스추천",
        "반려견동반카페","반려견동반여행","강아지동반숙소",
    ]},
    "cat":           {"label": "🐱 고양이", "seeds": [
        "고양이입양방법","고양이품종추천","고양이입양비용","길고양이입양",
        "고양이사료추천","고양이습식사료추천","고양이간식추천","고양이물먹이기",
        "고양이중성화수술","고양이예방접종","고양이건강검진",
        "고양이구내염","고양이신부전","고양이구토원인",
        "고양이화장실추천","고양이모래추천","캣타워추천","고양이장난감추천",
        "고양이목욕방법","고양이털관리","고양이발톱관리","고양이행동의미",
    ]},
    "interior":      {"label": "🏠 인테리어", "seeds": [
        "원룸인테리어","신혼집인테리어","거실인테리어","침실인테리어","주방인테리어","욕실인테리어",
        "셀프인테리어방법","도배셀프방법","페인트셀프칠하기",
        "조명추천","무드등추천","가구추천","소파추천","침대추천","식탁추천",
        "이케아추천","다이소인테리어","수납아이디어","정리정돈방법",
        "인테리어소품추천","액자추천","화분추천","커튼추천","러그추천",
        "미니멀인테리어","북유럽인테리어","이사준비체크리스트",
    ]},
    "living":        {"label": "🧹 생활 / 살림 / 청소", "seeds": [
        "청소방법","대청소순서","화장실청소방법","욕실청소","주방청소","곰팡이제거방법",
        "세탁방법","흰옷세탁법","니트세탁법","침구세탁","옷관리방법","패딩세탁방법",
        "살림꿀팁","주부꿀팁","생활꿀팁","천연세제만들기","베이킹소다활용","구연산활용법",
        "청소기추천","청소도구추천","식물키우기","반려식물추천","공기정화식물추천",
        "다육이키우기","몬스테라키우기","절전방법","수도세절약",
    ]},
    "self_dev":      {"label": "🎓 자기계발 / 취미", "seeds": [
        "자기계발방법","성공습관","아침루틴만들기","독서습관","책추천자기계발",
        "영어공부방법","영어회화독학","토익공부방법","오픽공부",
        "자격증추천","취업자격증","컴활자격증","공무원시험준비","취업준비방법",
        "이력서쓰는법","자기소개서작성법","면접준비방법",
        "그림독학방법","수채화그리기","뜨개질초보","자수배우기",
        "사진촬영기초","기타독학방법","피아노독학","등산초보장비",
        "캠핑초보장비","캠핑용품추천","서핑배우기","낚시입문방법",
    ]},
}

# ═══════════════════════════════════════════
# 주제별 관련성 필터 (하나라도 포함해야 통과)
# ═══════════════════════════════════════════
TOPIC_FILTERS = {
    # ── 음식 ──────────────────────────────────────────────────────────────
    "korean_food":   ["레시피","만들기","요리법","집밥","찌개","볶음","조림","반찬","김치","나물","무침","구이법","갈비","불고기","잡채","제육","닭볶","비빔","된장","순두부","떡볶이","삼겹","밑반찬","도시락","한식","에어프라이어"],
    "world_food":    ["파스타","피자","스테이크","리조또","짜장면","짬뽕","라멘","우동","돈카츠","카레만들기","크림파스타","오일파스타","까르보나라","타코","부리또","볶음밥","중식","일식","양식요리"],
    "diet_food":     ["다이어트","칼로리","식단","저탄고지","키토","클린이팅","단백질","체중감량","닭가슴살","샐러드","저당식","건강식단","뱃살","간헐적단식","저칼로리"],
    "baking":        ["케이크","쿠키","베이킹","마카롱","타르트","디저트","반죽","브라우니","머핀","스콘","와플","파운드","시폰","치즈케이크","식빵","소금빵","도넛","크로플"],
    "cafe_drinks":   ["커피","라떼","에이드","스무디","홈카페","버블티","음료만들기","아이스커피","콜드브루","달고나","청만들기","레몬에이드","홈카페레시피","시럽만들기","말차라떼"],
    # ── 건강/운동 ──────────────────────────────────────────────────────────
    "fitness":       ["헬스","운동루틴","홈트","스쿼트","데드리프트","벤치프레스","근력운동","체지방","맨몸운동","덤벨","코어운동","복근","하체운동","어깨운동","등운동","유산소","헬스초보","프로틴"],
    "yoga":          ["요가","필라테스","스트레칭","명상방법","폼롤러","근막이완","마음챙김","호흡법","요가자세","필라테스효과","요가루틴","유연성","골반교정","척추교정"],
    "health":        ["건강검진","질환","증상","치료방법","통증","예방법","면역력","혈압관리","혈당관리","콜레스테롤","관절염","디스크","위염","장염","피로회복","불면증","갱년기","고혈압","당뇨"],
    "supplements":   ["영양제","비타민","유산균","오메가3","프로바이오틱스","건강기능식품","효능","마그네슘","아연","콜라겐","루테인","홍삼","밀크씨슬","영양제추천","보충제"],
    # ── 뷰티 ──────────────────────────────────────────────────────────────
    "skincare":      ["스킨케어","피부관리","피부타입","크림추천","세럼","앰플","토너","선크림","화장품","모공","여드름","미백","주름","보습","각질","클렌징","마스크팩","기초화장"],
    "makeup":        ["메이크업","파운데이션","립스틱","아이섀도","마스카라","네일","눈썹","컨실러","쿠션팩트","블러셔","하이라이터","아이라이너","데일리메이크업","웨딩메이크업","색조"],
    "fashion_w":     ["여성코디","여자코디","데일리룩","오피스룩","원피스코디","스커트코디","블라우스","여성패션","봄코디","여름코디","가을코디","겨울코디","여성신발","여성가방","체형코디"],
    "fashion_m":     ["남자코디","남성코디","남자패션","남성패션","남자데일리","남자오피스","청바지코디남","슬랙스코디","남자셔츠","남자니트","남자패딩","남성신발추천","남자가방"],
    "hair":          ["헤어스타일","머리스타일","염색방법","파마추천","샴푸추천","두피관리","탈모예방","트리트먼트","헤어팩","헤어에센스","헤어드라이기","고데기","단발머리","중단발","울프컷"],
    # ── 육아 ──────────────────────────────────────────────────────────────
    "pregnancy":     ["임신","출산","태교","산후조리","모유수유","신생아","태아발달","임산부","분만","입덧","태동","임신초기","임신중","산후"],
    "baby":          ["아기","신생아","이유식","분유추천","기저귀","수유","아기발달","아기잠","아기용품","아기간식","육아","영아","개월아기","아기목욕","아기울음"],
    "kids_edu":      ["어린이","유아교육","아동","유치원","어린이집","초등","훈육방법","아이발달","그림책","장난감추천","한글공부","영어교육유아","아이독서","어린이영양"],
    # ── 여행 ──────────────────────────────────────────────────────────────
    "dom_travel":    ["국내여행","여행코스","당일치기","1박2일","2박3일","드라이브코스","여행지추천","커플여행","가족여행","혼자여행","제주여행","부산여행","경주여행","강릉여행","속초여행"],
    "ovs_travel":    ["해외여행","일본여행","태국여행","베트남여행","유럽여행","미국여행","오사카여행","도쿄여행","방콕여행","다낭여행","발리여행","대만여행","괌여행","해외여행코스","해외여행준비"],
    "restaurant":    ["맛집","식당추천","음식점","고기집","초밥맛집","라멘맛집","파스타맛집","분위기좋은","가성비식당","혼밥맛집","데이트맛집","줄서는맛집","숨은맛집","서울맛집","부산맛집"],
    "cafe":          ["카페추천","카페투어","감성카페","디저트카페","케이크맛집","빵집","크로플","마카롱맛집","소금빵","빙수맛집","브런치카페","루프탑카페","애견카페","책카페"],
    "accommodation": ["숙소추천","펜션추천","호텔추천","글램핑","풀빌라","오션뷰숙소","한옥스테이","감성숙소","독채펜션","커플펜션","가족펜션","리조트추천","반려동물펜션","수영장펜션"],
    # ── 재테크 ────────────────────────────────────────────────────────────
    "stock":         ["주식투자","주식공부","ETF투자","배당주","코인투자","펀드","증권","수익률","포트폴리오","주식분석","주식매매","미국주식","배당금","주식초보","ETF추천"],
    "realestate":    ["아파트청약","부동산투자","청약방법","전세계약","월세","주택담보대출","분양","임대사업","재개발","재건축","오피스텔","경매투자","전세사기","아파트매매","청약통장"],
    "saving":        ["절약방법","재테크","가계부","신용카드추천","포인트적립","통신비절약","생활비절약","적금추천","예금금리","소비줄이기","저축방법","짠테크","카드혜택","연말정산","부업"],
    # ── IT/가전 ────────────────────────────────────────────────────────────
    "laptop":        ["노트북추천","노트북비교","맥북","PC추천","모니터추천","키보드추천","마우스추천","냉장고추천","세탁기추천","청소기추천","에어컨추천","공기청정기","이어폰추천","헤드폰","가전제품"],
    "smartphone":    ["스마트폰추천","아이폰","갤럭시","앱추천","스마트폰비교","아이패드","갤럭시탭","유튜브수익","블로그수익","챗GPT","AI활용","인스타그램","유튜브알고리즘","스마트스토어"],
    # ── 반려동물 ──────────────────────────────────────────────────────────
    "dog":           ["강아지","반려견","강아지사료","강아지훈련","강아지간식","강아지용품","강아지미용","강아지건강","강아지질병","강아지예방접종","강아지목욕","반려견동반","강아지품종"],
    "cat":           ["고양이","반려묘","고양이사료","고양이간식","고양이화장실","캣타워","고양이장난감","고양이건강","고양이질병","고양이중성화","고양이모래","고양이털","고양이행동"],
    # ── 생활 ──────────────────────────────────────────────────────────────
    "interior":      ["인테리어","셀프인테리어","인테리어소품","가구추천","조명추천","수납아이디어","이케아","다이소인테리어","러그추천","커튼추천","소파추천","침대추천","거실인테리어","원룸인테리어"],
    "living":        ["청소방법","대청소","세탁방법","살림꿀팁","주부꿀팁","정리정돈","수납방법","빨래관리","청소꿀팁","천연세제","베이킹소다","구연산","곰팡이제거","청소기추천","정리법"],
    "self_dev":      ["자기계발","공부방법","자격증추천","취업준비","영어공부","독서습관","취미생활","아침루틴","성공습관","자격증공부","이력서","면접준비","스킬향상","온라인강의","부업"],
}

# ═══════════════════════════════════════════
# 히스토리
# ═══════════════════════════════════════════
def load_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_history(h):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False, indent=2)

# ═══════════════════════════════════════════
# 스캔 결과 파일 (주제별)
# ═══════════════════════════════════════════
def scan_file(topic):
    return f"scan_{topic}.json"

def load_scan(topic):
    try:
        with open(scan_file(topic), "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_scan(new_items, topic):
    existing = load_scan(topic)
    kws = {r["keyword"] for r in existing}
    for item in new_items:
        if item["keyword"] not in kws:
            existing.append(item)
            kws.add(item["keyword"])
    existing.sort(key=lambda x: x["srch"] - x["doc"], reverse=True)
    with open(scan_file(topic), "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

# ═══════════════════════════════════════════
# Naver API
# ═══════════════════════════════════════════
def _ad_header(method, uri):
    ts  = str(int(time.time() * 1000))
    msg = f"{ts}.{method}.{uri}"
    sig = base64.b64encode(
        hmac.new(AD_SECRET_KEY.encode(), msg.encode(), hashlib.sha256).digest()
    ).decode()
    return {"Content-Type": "application/json; charset=UTF-8",
            "X-Timestamp": ts, "X-API-KEY": AD_API_KEY,
            "X-Customer": AD_CUSTOMER_ID, "X-Signature": sig}

def _parse(v):
    return 5 if str(v) == "< 10" else int(v or 0)

def get_doc(kw):
    try:
        r = blog_session.get(
            "https://openapi.naver.com/v1/search/blog.json",
            params={"query": kw, "display": 1, "sort": "sim"}, timeout=8)
        return int(r.json().get("total", 0)) if r.status_code == 200 else -1
    except:
        return -1

def get_srch(kw):
    uri  = "/keywordstool"
    hint = kw.replace(" ", "")
    try:
        r = ad_session.get("https://api.naver.com" + uri,
                           headers=_ad_header("GET", uri),
                           params={"hintKeywords": hint, "showDetail": "1",
                                   "includeHintKeywords": "1"}, timeout=12)
        if r.status_code != 200:
            return {"pc": 0, "mob": 0, "total": 0}
        for item in r.json().get("keywordList", []):
            if item.get("relKeyword", "").replace(" ", "") == hint:
                pc  = _parse(item.get("monthlyPcQcCnt",     "0"))
                mob = _parse(item.get("monthlyMobileQcCnt", "0"))
                return {"pc": pc, "mob": mob, "total": pc + mob}
        return {"pc": 0, "mob": 0, "total": 0}
    except:
        return {"pc": 0, "mob": 0, "total": -1}

def get_related(seeds):
    uri   = "/keywordstool"
    hints = ",".join(s.replace(" ", "") for s in seeds[:5])
    try:
        r = ad_session.get("https://api.naver.com" + uri,
                           headers=_ad_header("GET", uri),
                           params={"hintKeywords": hints, "showDetail": "1",
                                   "includeHintKeywords": "1"}, timeout=12)
        if r.status_code != 200:
            return {}
        out = {}
        for item in r.json().get("keywordList", []):
            kw = item.get("relKeyword", "").strip()
            if not kw:
                continue
            pc  = _parse(item.get("monthlyPcQcCnt",     "0"))
            mob = _parse(item.get("monthlyMobileQcCnt", "0"))
            out[kw] = {"pc": pc, "mob": mob, "total": pc + mob}
        return out
    except:
        return {}

def judge(doc, srch):
    if doc < 0:
        return {"g": "분석불가", "e": "❓", "c": "#6b7280"}
    ld = doc <= GOLD_MAX_DOCS
    hs = srch >= 500
    md = doc <= 8000
    if ld and hs:        return {"g": "황금키워드",      "e": "🏆", "c": "#F5A623"}
    if ld and srch <= 0: return {"g": "검색량확인필요",  "e": "🔍", "c": "#9B59B6"}
    if ld:               return {"g": "블루오션",         "e": "🌊", "c": "#3498DB"}
    if md and hs:        return {"g": "추천",             "e": "✅", "c": "#27AE60"}
    if md:               return {"g": "보통",             "e": "⚠️",  "c": "#E67E22"}
    return                     {"g": "경쟁과다",          "e": "❌", "c": "#E74C3C"}

# ═══════════════════════════════════════════
# 자동 발굴 백그라운드
# ═══════════════════════════════════════════
def run_scan(target, topic_key, min_search, comp_ratio=0.5):
    info        = TOPICS.get(topic_key, {})
    label       = info.get("label", topic_key)
    seeds       = info.get("seeds", [])
    stop_event  = threading.Event()
    found_list  = []

    try:
        with scan_lock:
            scan_state.update({"running": True, "progress": 0, "checked": 0,
                                "found": 0, "results": [], "log": [], "phase":
                                f"[{label}] 연관 키워드 수집 중..."})

        # ── Phase 1: 시드 배치 병렬 keywordstool (6 workers) ──
        batches = [seeds[i:i+5] for i in range(0, len(seeds), 5)]
        all_kw  = {}
        done_seeds = 0

        with ThreadPoolExecutor(max_workers=6) as ex:
            fmap = {ex.submit(get_related, b): b for b in batches}
            for f in as_completed(fmap):
                if not scan_state["running"]:
                    break
                all_kw.update(f.result())
                done_seeds += len(fmap[f])
                with scan_lock:
                    scan_state["log"].append(
                        f"시드 {done_seeds}/{len(seeds)} 처리 → 연관어 {len(all_kw)}개")

        # ── 사전 필터 1: 최소 검색량 & 기존 제외 (상한 없음) ──
        existing = {r["keyword"] for r in load_scan(topic_key)}
        candidates = {k: v for k, v in all_kw.items()
                      if v["total"] >= min_search and k not in existing}

        # ── 사전 필터 2: 주제 관련 키워드만 통과 ──
        include_words = TOPIC_FILTERS.get(topic_key, [])
        if include_words:
            before = len(candidates)
            candidates = {k: v for k, v in candidates.items()
                          if any(w in k for w in include_words)}
            with scan_lock:
                scan_state["log"].append(
                    f"관련성 필터: {before}개 → {len(candidates)}개 (무관 키워드 {before-len(candidates)}개 제거)")

        # 검색량 높은 순 정렬 → 황금 가능성 높은 것 먼저
        kw_items = sorted(candidates.items(), key=lambda x: x[1]["total"], reverse=True)

        with scan_lock:
            scan_state["total"] = len(kw_items)
            scan_state["phase"] = f"[{label}] 발행량 조회 중 (후보 {len(kw_items)}개)..."
            scan_state["log"].append(f"후보 {len(kw_items)}개 → 25스레드 병렬 조회 시작")

        # ── Phase 2: 25 스레드 병렬 블로그 발행량 조회 ──
        def check(item):
            if stop_event.is_set():
                return None
            kw, sr = item
            return kw, sr, get_doc(kw)

        with ThreadPoolExecutor(max_workers=25) as ex:
            fmap = {ex.submit(check, item): item for item in kw_items}
            for f in as_completed(fmap):
                if stop_event.is_set():
                    break
                res = f.result()
                if res is None:
                    continue
                kw, sr, doc = res

                with scan_lock:
                    scan_state["checked"] += 1
                    scan_state["progress"] = int(
                        scan_state["checked"] / max(scan_state["total"], 1) * 100)

                if doc >= 0 and doc > 0 and sr["total"] >= doc * comp_ratio:
                    j = judge(doc, sr["total"])
                    entry = {
                        "keyword":     kw,
                        "topic":       topic_key,
                        "doc":         doc,
                        "srch":        sr["total"],
                        "pc":          sr["pc"],
                        "mob":         sr["mob"],
                        "comp":        round(doc / sr["total"], 2) if sr["total"] else None,
                        "grade":       j["g"], "emoji": j["e"], "color": j["c"],
                        "searched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "blog_link":   f"https://search.naver.com/search.naver?where=blog&query={quote(kw)}",
                        "ad_link":     f"https://manage.searchad.naver.com/customers/keywordstool?keywords={quote(kw)}",
                    }
                    with scan_lock:
                        scan_state["found"] += 1
                        scan_state["results"].append(entry)
                        found_list.append(entry)
                        if scan_state["found"] % 5 == 0:
                            scan_state["log"].append(f"🏆 황금키워드 {scan_state['found']}개 발견!")

                    if scan_state["found"] >= target:
                        stop_event.set()
                        with scan_lock:
                            scan_state["log"].append(f"목표 {target}개 달성!")
                        break

                if not scan_state["running"]:
                    stop_event.set()
                    break

        save_scan(found_list, topic_key)
        with scan_lock:
            scan_state["running"] = False
            scan_state["phase"]   = f"완료! [{label}] 황금키워드 {scan_state['found']}개 발굴"

    except Exception as e:
        with scan_lock:
            scan_state["running"] = False
            scan_state["phase"]   = f"오류: {e}"

# ═══════════════════════════════════════════
# Flask 라우트
# ═══════════════════════════════════════════
@app.route("/search", methods=["POST"])
def search():
    kw = (request.json or {}).get("keyword", "").strip()
    if not kw:
        return jsonify({"error": "키워드를 입력하세요"}), 400
    doc  = get_doc(kw)
    sr   = get_srch(kw)
    srch = sr["total"]
    j    = judge(doc, srch)
    result = {
        "keyword": kw, "doc": doc, "srch": srch,
        "pc": sr["pc"], "mob": sr["mob"],
        "comp": round(doc / srch, 2) if doc > 0 and srch > 0 else None,
        "grade": j["g"], "emoji": j["e"], "color": j["c"],
        "searched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "blog_link": f"https://search.naver.com/search.naver?where=blog&query={quote(kw)}",
        "ad_link":   f"https://manage.searchad.naver.com/customers/keywordstool?keywords={quote(kw)}",
    }
    h = load_history()
    h = [x for x in h if x["keyword"] != kw]
    h.insert(0, result)
    save_history(h)
    return jsonify(result)

@app.route("/history")
def get_history():
    return jsonify(load_history())

@app.route("/history/delete", methods=["POST"])
def del_history():
    kw = (request.json or {}).get("keyword", "")
    h  = [x for x in load_history() if x["keyword"] != kw]
    save_history(h)
    return jsonify({"ok": True})

@app.route("/history/clear", methods=["POST"])
def clear_history():
    save_history([])
    return jsonify({"ok": True})

@app.route("/golden-all")
def golden_all():
    h = load_history()
    r = sorted([x for x in h if x.get("srch", 0) > x.get("doc", 0) > 0],
               key=lambda x: x["srch"] - x["doc"], reverse=True)
    return jsonify(r)

@app.route("/scan/topics")
def scan_topics():
    return jsonify({k: v["label"] for k, v in TOPICS.items()})

@app.route("/scan/start", methods=["POST"])
def scan_start():
    if scan_state["running"]:
        return jsonify({"error": "이미 발굴 중입니다"}), 400
    data       = request.json or {}
    topic      = data.get("topic", "")
    target     = max(1, int(data.get("target", 100)))
    min_search = max(100, min(20000, int(data.get("min_search", 1000))))
    comp_ratio = max(0.1, min(1.0, float(data.get("comp_ratio", 0.5))))
    if topic not in TOPICS:
        return jsonify({"error": "주제를 선택해주세요"}), 400
    threading.Thread(target=run_scan, args=(target, topic, min_search, comp_ratio), daemon=True).start()
    return jsonify({"ok": True})

@app.route("/scan/stop", methods=["POST"])
def scan_stop():
    with scan_lock:
        scan_state["running"] = False
        scan_state["phase"]   = "중단됨"
    return jsonify({"ok": True})

@app.route("/scan/status")
def scan_status():
    with scan_lock:
        return jsonify({
            "running":  scan_state["running"],
            "progress": scan_state["progress"],
            "total":    scan_state["total"],
            "checked":  scan_state["checked"],
            "found":    scan_state["found"],
            "phase":    scan_state["phase"],
            "log":      scan_state["log"][-6:],
            "results":  scan_state["results"][-30:],
        })

@app.route("/scan/results")
def scan_results():
    topic   = request.args.get("topic", "")
    results = load_scan(topic)
    # 저장된 과거 데이터에도 관련성 필터 소급 적용
    words = TOPIC_FILTERS.get(topic, [])
    if words:
        results = [r for r in results if any(w in r["keyword"] for w in words)]
        results.sort(key=lambda x: x["srch"] - x["doc"], reverse=True)
    return jsonify(results)

@app.route("/scan/clear", methods=["POST"])
def scan_clear():
    topic = (request.json or {}).get("topic", "")
    if topic in TOPICS:
        with open(scan_file(topic), "w", encoding="utf-8") as f:
            json.dump([], f)
    return jsonify({"ok": True})

# ═══════════════════════════════════════════
# HTML
# ═══════════════════════════════════════════
HTML = """<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>키워드 분석기</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&family=IBM+Plex+Mono:wght@400;600&display=swap');
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0b0d12;--s1:#13161e;--s2:#1a1e28;--bd:#252a38;--tx:#dde1ec;--mt:#5a6178;--f:'Noto Sans KR',sans-serif;--m:'IBM Plex Mono',monospace;--gold:#F5A623}
body{background:var(--bg);color:var(--tx);font-family:var(--f);min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:28px 16px}

/* 헤더 */
.hdr{text-align:center;margin-bottom:24px;width:100%;max-width:860px}
.htag{display:inline-block;font-family:var(--m);font-size:10px;letter-spacing:3px;color:var(--gold);background:#F5A62312;border:1px solid #F5A62328;padding:3px 14px;border-radius:20px;margin-bottom:8px}
h1{font-size:clamp(22px,5vw,38px);font-weight:900;background:linear-gradient(120deg,#fff 30%,var(--gold));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin-bottom:4px}
.hsub{color:var(--mt);font-family:var(--m);font-size:11px}

/* 탭 */
.tabs{display:flex;width:100%;max-width:860px;margin-bottom:24px;background:var(--s1);border:1px solid var(--bd);border-radius:14px;overflow:hidden}
.tab-btn{flex:1;background:none;border:none;padding:12px 0;font-family:var(--f);font-size:13px;font-weight:700;color:var(--mt);cursor:pointer;transition:all .2s;border-bottom:2px solid transparent}
.tab-btn.active{color:var(--gold);border-bottom-color:var(--gold);background:var(--s2)}
.tab-btn:hover:not(.active){color:var(--tx)}
.tab-page{display:none;width:100%;max-width:860px}
.tab-page.active{display:block}

/* 검색창 */
.search-wrap{margin-bottom:24px}
.search-box{display:flex;gap:10px;background:var(--s1);border:1px solid var(--bd);border-radius:14px;padding:12px 16px;transition:border-color .2s}
.search-box:focus-within{border-color:var(--gold)}
.search-box input{flex:1;background:none;border:none;color:var(--tx);font-family:var(--f);font-size:16px;outline:none}
.search-box input::placeholder{color:var(--mt)}
.search-box button{background:var(--gold);color:#000;border:none;padding:10px 22px;border-radius:10px;font-family:var(--f);font-size:14px;font-weight:700;cursor:pointer;transition:opacity .15s;white-space:nowrap}
.search-box button:hover{opacity:.85}
.search-box button:disabled{opacity:.4;cursor:not-allowed}
.loading{display:none;text-align:center;padding:14px;color:var(--mt);font-family:var(--m);font-size:12px}
.spinner{display:inline-block;width:14px;height:14px;border:2px solid var(--bd);border-top-color:var(--gold);border-radius:50%;animation:spin .7s linear infinite;margin-right:6px;vertical-align:middle}
@keyframes spin{to{transform:rotate(360deg)}}

/* 결과 카드 */
.result-card{display:none;background:var(--s1);border:1px solid var(--bd);border-radius:14px;overflow:hidden;margin-bottom:24px;animation:slideIn .3s ease}
@keyframes slideIn{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:none}}
.card-header{padding:16px 20px;border-bottom:1px solid var(--bd);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px}
.card-kw{font-size:20px;font-weight:900}
.badge{display:inline-block;padding:5px 12px;border-radius:20px;font-size:12px;font-weight:700;border:1px solid;white-space:nowrap}
.card-body{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--bd)}
.metric{background:var(--s1);padding:16px 20px;text-align:center}
.metric-label{font-size:10px;color:var(--mt);font-family:var(--m);letter-spacing:1px;margin-bottom:6px;text-transform:uppercase}
.metric-value{font-size:26px;font-weight:900;font-family:var(--m);line-height:1}
.metric-sub{font-size:10px;color:var(--mt);margin-top:4px}
.card-footer{padding:10px 20px;border-top:1px solid var(--bd);display:flex;gap:10px;flex-wrap:wrap}
.card-footer a{font-size:10px;font-family:var(--m);color:var(--mt);text-decoration:none;padding:4px 10px;border:1px solid var(--bd);border-radius:5px;transition:all .15s}
.card-footer a:hover{color:var(--gold);border-color:#F5A62366}
.comp-green{color:#2ECC71}.comp-yellow{color:#F5A623}.comp-red{color:#E74C3C}

/* 황금 모음 */
.gold-section{margin-bottom:20px}
.gold-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
.gold-title{font-size:12px;font-weight:700;color:var(--gold);font-family:var(--m);letter-spacing:1px}
.gold-count{font-family:var(--m);font-size:10px;color:var(--mt);background:var(--s1);border:1px solid var(--bd);padding:3px 10px;border-radius:20px}
.btn-gold-toggle{background:var(--gold);color:#000;border:none;padding:5px 14px;border-radius:8px;font-size:11px;font-weight:700;cursor:pointer;font-family:var(--m)}
.gold-list{display:flex;flex-direction:column;gap:5px}
.gold-item{background:var(--s1);border:1px solid #F5A62330;border-radius:10px;padding:10px 14px;display:flex;align-items:center;gap:10px;cursor:pointer;transition:all .2s}
.gold-item:hover{border-color:#F5A62388;background:var(--s2)}
.gold-kw{font-size:13px;font-weight:700;color:var(--gold);flex:1}
.gold-stats{font-family:var(--m);font-size:10px;color:var(--mt);display:flex;gap:8px;flex-wrap:wrap}
.gold-ratio{font-family:var(--m);font-size:11px;font-weight:700;color:#2ECC71;background:#2ECC7118;border:1px solid #2ECC7128;padding:2px 8px;border-radius:12px;white-space:nowrap}
.gold-empty{text-align:center;padding:24px;color:var(--mt);font-family:var(--m);font-size:12px}

/* 히스토리 */
.history-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
.history-title{font-size:12px;font-weight:700;color:var(--mt);font-family:var(--m);letter-spacing:1px}
.btn-clear{background:none;border:1px solid var(--bd);color:var(--mt);padding:4px 10px;border-radius:6px;font-size:10px;cursor:pointer;font-family:var(--m)}
.btn-clear:hover{color:#E74C3C;border-color:#E74C3C44}
.history-list{display:flex;flex-direction:column;gap:5px}
.history-item{background:var(--s1);border:1px solid var(--bd);border-radius:10px;padding:10px 14px;display:flex;align-items:center;gap:10px;cursor:pointer;transition:all .2s;animation:fu .2s ease}
@keyframes fu{from{opacity:0;transform:translateX(-4px)}to{opacity:1;transform:none}}
.history-item:hover{border-color:#35394a;background:var(--s2)}
.hi-kw{font-size:13px;font-weight:700;flex:1}
.hi-stats{font-family:var(--m);font-size:10px;color:var(--mt);display:flex;gap:8px;flex-wrap:wrap}
.hi-grade{margin-left:auto;display:flex;align-items:center;gap:6px}
.hi-time{font-family:var(--m);font-size:9px;color:var(--mt);opacity:.6}
.btn-del{background:none;border:none;color:var(--mt);cursor:pointer;font-size:12px;opacity:.4;transition:opacity .15s;padding:0 2px}
.btn-del:hover{opacity:1;color:#E74C3C}
.divider{width:100%;border:none;border-top:1px solid var(--bd);margin:0 0 20px}

/* 자동발굴 */
.scan-box{background:var(--s1);border:1px solid var(--bd);border-radius:14px;padding:20px;margin-bottom:18px}
.scan-step-label{font-family:var(--m);font-size:10px;color:var(--mt);letter-spacing:1px;margin-bottom:8px;display:block}
.topic-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:6px;margin-bottom:0}
.topic-btn{background:var(--s2);border:1px solid var(--bd);color:var(--mt);padding:8px 4px;border-radius:9px;font-family:var(--f);font-size:11px;font-weight:700;cursor:pointer;transition:all .2s;text-align:center;line-height:1.4}
.topic-btn:hover{border-color:#F5A62366;color:var(--tx)}
.topic-btn.sel{background:#F5A62318;border-color:var(--gold);color:var(--gold)}
.scan-mid{padding-top:14px;border-top:1px solid var(--bd);margin-top:14px}
.min-label{font-family:var(--m);font-size:10px;color:var(--mt);display:flex;justify-content:space-between;margin-bottom:6px}
.min-label b{color:var(--gold)}
input[type=range]{-webkit-appearance:none;width:100%;height:4px;background:var(--bd);border-radius:4px;outline:none}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:15px;height:15px;background:var(--gold);border-radius:50%;cursor:pointer}
.range-marks{display:flex;justify-content:space-between;font-family:var(--m);font-size:9px;color:var(--mt);margin-top:4px}
.comp-select{background:var(--s2);border:1px solid var(--bd);color:var(--tx);font-family:var(--m);font-size:12px;padding:7px 10px;border-radius:8px;outline:none;cursor:pointer}
.comp-select:focus{border-color:var(--gold)}
.scan-ctrl{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding-top:14px}
.ctrl-label{font-family:var(--m);font-size:11px;color:var(--mt)}
.ctrl-num{background:var(--s2);border:1px solid var(--bd);color:var(--tx);font-family:var(--m);font-size:14px;font-weight:700;padding:6px 10px;border-radius:8px;width:68px;text-align:center;outline:none}
.ctrl-num:focus{border-color:var(--gold)}
.btn-start{background:var(--gold);color:#000;border:none;padding:10px 22px;border-radius:10px;font-weight:700;font-size:14px;cursor:pointer;font-family:var(--f)}
.btn-start:hover{opacity:.85}
.btn-start:disabled{opacity:.4;cursor:not-allowed}
.btn-stop{background:none;border:1px solid #E74C3C55;color:#E74C3C;padding:10px 16px;border-radius:10px;font-weight:700;font-size:13px;cursor:pointer;font-family:var(--f)}
.btn-stop:hover{background:#E74C3C15}
.btn-clear-scan{background:none;border:1px solid var(--bd);color:var(--mt);padding:6px 12px;border-radius:8px;font-size:10px;cursor:pointer;font-family:var(--m);margin-left:auto}
.btn-clear-scan:hover{color:#E74C3C;border-color:#E74C3C44}

/* 진행 */
.scan-prog{margin-top:16px}
.prog-phase{font-family:var(--m);font-size:11px;color:var(--mt);margin-bottom:6px}
.prog-bar-bg{background:var(--s2);border-radius:20px;height:6px;overflow:hidden}
.prog-bar{background:linear-gradient(90deg,var(--gold),#f7c948);height:100%;border-radius:20px;transition:width .4s ease;width:0%}
.prog-stats{display:flex;gap:14px;margin-top:8px;flex-wrap:wrap;align-items:baseline}
.prog-stat{font-family:var(--m);font-size:10px;color:var(--mt)}
.prog-stat b{color:var(--tx)}
.found-num{font-family:var(--m);font-size:28px;font-weight:700;color:var(--gold);line-height:1}
.prog-log{background:var(--s2);border-radius:8px;padding:8px 12px;font-family:var(--m);font-size:10px;color:var(--mt);margin-top:10px;min-height:36px;line-height:1.9}

/* 결과 목록 */
.result-header{display:flex;align-items:center;justify-content:space-between;margin:14px 0 8px}
.result-title{font-family:var(--m);font-size:10px;color:var(--mt);letter-spacing:1px}
.result-count{font-family:var(--m);font-size:10px;color:var(--mt)}
.result-list{display:flex;flex-direction:column;gap:5px}
.result-item{background:var(--s1);border:1px solid #F5A62330;border-radius:10px;padding:10px 14px;display:flex;align-items:center;gap:10px;cursor:pointer;transition:all .2s}
.result-item:hover{border-color:#F5A62388;background:var(--s2)}
.ri-kw{font-size:13px;font-weight:700;color:var(--gold);flex:1}
.ri-stats{font-family:var(--m);font-size:10px;color:var(--mt);display:flex;gap:8px;flex-wrap:wrap}
.ri-ratio{font-family:var(--m);font-size:11px;font-weight:700;color:#2ECC71;background:#2ECC7118;border:1px solid #2ECC7128;padding:2px 8px;border-radius:12px;white-space:nowrap}
.empty-msg{text-align:center;padding:24px;color:var(--mt);font-family:var(--m);font-size:12px}

@media(max-width:640px){.topic-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:420px){.card-body{grid-template-columns:1fr}.hi-stats,.ri-stats,.gold-stats{display:none}.topic-grid{grid-template-columns:repeat(2,1fr)}}
</style></head>
<body>

<div class="hdr">
  <div class="htag">KEYWORD ANALYZER</div>
  <h1>키워드 분석기</h1>
  <p class="hsub">즉석 분석 · 황금키워드 자동 발굴</p>
</div>

<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('search')">🔍 즉석 분석</button>
  <button class="tab-btn" onclick="switchTab('scan')">🏆 자동 발굴</button>
  <button class="tab-btn" onclick="switchTab('history')">📋 히스토리</button>
</div>

<!-- ══ 탭1: 즉석 분석 ══ -->
<div class="tab-page active" id="tab-search">
  <div class="search-wrap">
    <div class="search-box">
      <input id="kwInput" type="text" placeholder="키워드 입력 (예: 가평 커플 펜션)"
             onkeydown="if(event.key==='Enter')doSearch()">
      <button id="searchBtn" onclick="doSearch()">분석하기</button>
    </div>
    <div class="loading" id="loading"><span class="spinner"></span>네이버 API 조회 중...</div>
  </div>

  <div class="result-card" id="resultCard">
    <div class="card-header">
      <span class="card-kw" id="resKw"></span>
      <span class="badge" id="resBadge"></span>
    </div>
    <div class="card-body">
      <div class="metric">
        <div class="metric-label">월 발행량</div>
        <div class="metric-value" id="resDoc"></div>
        <div class="metric-sub">건</div>
      </div>
      <div class="metric">
        <div class="metric-label">월 검색수</div>
        <div class="metric-value" id="resSrch"></div>
        <div class="metric-sub" id="resPcMob"></div>
      </div>
      <div class="metric">
        <div class="metric-label">경쟁지수</div>
        <div class="metric-value" id="resComp"></div>
        <div class="metric-sub" id="resCompLbl"></div>
      </div>
    </div>
    <div class="card-footer">
      <a id="blogLink" href="#" target="_blank">블로그 검색 ↗</a>
      <a id="adLink"  href="#" target="_blank">광고 키워드 도구 ↗</a>
    </div>
  </div>

  <div class="gold-section">
    <div class="gold-header">
      <span class="gold-title">🏆 검색기록 황금키워드</span>
      <div style="display:flex;align-items:center;gap:8px">
        <span class="gold-count" id="goldCount">0개</span>
        <button class="btn-gold-toggle" onclick="toggleGold()" id="goldToggleBtn">펼치기</button>
      </div>
    </div>
    <div id="goldWrap" style="display:none">
      <div class="gold-list" id="goldList"></div>
    </div>
  </div>
</div>

<!-- ══ 탭2: 자동 발굴 ══ -->
<div class="tab-page" id="tab-scan">
  <div class="scan-box">
    <span class="scan-step-label">STEP 1 · 분석할 주제 선택</span>
    <div class="topic-grid" id="topicGrid"></div>

    <div class="scan-mid">
      <div class="min-label">
        <span>STEP 2 · 최소 월검색량</span>
        <span>현재: <b id="minVal">1,000</b>회 이상</span>
      </div>
      <input type="range" id="minSlider" min="1000" max="20000" step="500" value="1000"
             oninput="document.getElementById('minVal').textContent=parseInt(this.value).toLocaleString()">
      <div class="range-marks"><span>1,000</span><span>5,000</span><span>10,000</span><span>15,000</span><span>20,000</span></div>
    </div>

    <div class="scan-ctrl">
      <span class="ctrl-label">경쟁강도</span>
      <select class="comp-select" id="compRatio">
        <option value="1.0">🥇 엄격 — 검색량 &gt; 발행량</option>
        <option value="0.7">👍 보통 — 검색량 ≥ 발행량×0.7</option>
        <option value="0.5" selected>👌 완화 — 검색량 ≥ 발행량×0.5</option>
        <option value="0.3">🔓 최대완화 — 검색량 ≥ 발행량×0.3</option>
      </select>
      <span class="ctrl-label" style="margin-left:6px">목표</span>
      <input class="ctrl-num" type="number" id="scanTarget" value="100" min="10" max="500">
      <span class="ctrl-label">개</span>
      <button class="btn-start" id="btnStart" onclick="startScan()">🚀 발굴 시작</button>
      <button class="btn-stop"  id="btnStop"  onclick="stopScan()" style="display:none">■ 중단</button>
      <button class="btn-clear-scan" onclick="clearScan()">결과 초기화</button>
    </div>

    <div class="scan-prog" id="scanProg" style="display:none">
      <div class="prog-phase" id="progPhase"></div>
      <div class="prog-bar-bg"><div class="prog-bar" id="progBar"></div></div>
      <div class="prog-stats">
        <span class="prog-stat">조회 <b id="progChecked">0</b>/<b id="progTotal">0</b></span>
        <span class="prog-stat">발견 <span class="found-num" id="progFound">0</span></span>
      </div>
      <div class="prog-log" id="progLog"></div>
    </div>
  </div>

  <div class="result-header">
    <span class="result-title">발굴된 황금키워드 (검색량 > 발행량)</span>
    <span class="result-count" id="scanResultCount">0개</span>
  </div>
  <div class="result-list" id="scanResultList">
    <div class="empty-msg">주제를 선택하고 발굴 시작 버튼을 누르세요</div>
  </div>
</div>

<!-- ══ 탭3: 히스토리 ══ -->
<div class="tab-page" id="tab-history">
  <div class="history-header">
    <span class="history-title">SEARCH HISTORY</span>
    <button class="btn-clear" onclick="clearAll()">전체 삭제</button>
  </div>
  <div class="history-list" id="historyList"></div>
</div>

<script>
const GD = 3000;

// ── 탭 ──────────────────────────────────────
function switchTab(t) {
  ['search','scan','history'].forEach((n,i) => {
    document.querySelectorAll('.tab-btn')[i].classList.toggle('active', n===t);
    document.getElementById('tab-'+n).classList.toggle('active', n===t);
  });
  if (t==='history') loadHistory();
  if (t==='scan')    loadScanResults();
}

// ── 즉석 분석 ────────────────────────────────
async function doSearch() {
  const kw = document.getElementById('kwInput').value.trim();
  if (!kw) return;
  document.getElementById('searchBtn').disabled = true;
  document.getElementById('loading').style.display = 'block';
  document.getElementById('resultCard').style.display = 'none';
  try {
    const res = await fetch('/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({keyword:kw})});
    const d = await res.json();
    if (d.error){alert(d.error);return;}
    showResult(d); loadHistory(); loadGolden();
  } catch(e){alert('오류: '+e.message);}
  finally{
    document.getElementById('searchBtn').disabled = false;
    document.getElementById('loading').style.display = 'none';
  }
}

function showResult(d) {
  document.getElementById('resKw').textContent = d.keyword;
  const badge = document.getElementById('resBadge');
  badge.textContent = d.emoji+' '+d.grade;
  badge.style.cssText = `color:${d.color};border-color:${d.color}44;background:${d.color}18`;

  const docEl = document.getElementById('resDoc');
  docEl.textContent = d.doc >= 0 ? d.doc.toLocaleString() : '—';
  docEl.style.color  = d.doc >= 0 && d.doc <= GD ? '#2ECC71' : d.doc > GD ? '#E74C3C' : '#6b7280';

  document.getElementById('resSrch').textContent = d.srch > 0 ? d.srch.toLocaleString() : (d.srch===0?'미확인':'실패');
  document.getElementById('resSrch').style.color  = d.srch > d.doc && d.srch > 0 ? '#F5A623' : '#dde1ec';
  document.getElementById('resPcMob').textContent = d.srch > 0 ? `PC ${d.pc.toLocaleString()} + 모바일 ${d.mob.toLocaleString()}` : '';

  const c = d.comp, cEl = document.getElementById('resComp'), cLbl = document.getElementById('resCompLbl');
  if (c !== null && c !== undefined) {
    cEl.textContent = c.toFixed(1);
    cEl.className = 'metric-value '+(c<=3?'comp-green':c<=10?'comp-yellow':'comp-red');
    cLbl.textContent = c<=3?'🟢 블루오션':c<=10?'🟡 보통':'🔴 경쟁 심함';
  } else { cEl.textContent='—'; cEl.className='metric-value'; cLbl.textContent='검색량 확인 필요'; }

  document.getElementById('blogLink').href = d.blog_link;
  document.getElementById('adLink').href   = d.ad_link;
  const card = document.getElementById('resultCard');
  card.style.display='block'; card.style.animation='none'; card.offsetHeight; card.style.animation='';
}

// ── 황금키워드 모음 ──────────────────────────
let goldOpen = false;
async function loadGolden() {
  const res = await fetch('/golden-all');
  const list = await res.json();
  const cnt = document.getElementById('goldCount');
  cnt.textContent = list.length+'개';
  cnt.style.color = list.length > 0 ? 'var(--gold)' : 'var(--mt)';
  const el = document.getElementById('goldList');
  if (!list.length) { el.innerHTML='<div class="gold-empty">검색량 > 발행량인 키워드가 없습니다</div>'; return; }
  el.innerHTML = list.map(d => {
    const ratio = d.doc > 0 ? (d.srch/d.doc).toFixed(1) : '∞';
    return `<div class="gold-item" onclick="reuseKw('${esc(d.keyword)}')">
      <span class="gold-kw">${esc(d.keyword)}</span>
      <div class="gold-stats">
        <span>발행 <b style="color:#dde1ec">${d.doc.toLocaleString()}</b></span>
        <span>검색 <b style="color:var(--gold)">${d.srch.toLocaleString()}</b></span>
      </div>
      <span class="gold-ratio">${ratio}×</span>
    </div>`;
  }).join('');
}
function toggleGold() {
  goldOpen = !goldOpen;
  document.getElementById('goldWrap').style.display = goldOpen ? 'block' : 'none';
  document.getElementById('goldToggleBtn').textContent = goldOpen ? '접기' : '펼치기';
  if (goldOpen) loadGolden();
}

// ── 히스토리 ─────────────────────────────────
async function loadHistory() {
  const res  = await fetch('/history');
  const list = await res.json();
  const el   = document.getElementById('historyList');
  if (!list.length) { el.innerHTML='<div class="empty-msg">검색 기록이 없습니다</div>'; return; }
  el.innerHTML = list.map(d => {
    const comp = d.comp !== null && d.comp !== undefined ? `경쟁 ${d.comp.toFixed(1)}` : '';
    return `<div class="history-item" onclick="reuseKw('${esc(d.keyword)}')">
      <span class="hi-kw">${esc(d.keyword)}</span>
      <div class="hi-stats">
        <span>발행 ${d.doc>=0?d.doc.toLocaleString():'—'}</span>
        <span>검색 ${d.srch>0?d.srch.toLocaleString():'미확인'}</span>
        ${comp?`<span>${comp}</span>`:''}
      </div>
      <div class="hi-grade">
        <span class="badge" style="color:${d.color};border-color:${d.color}44;background:${d.color}18;font-size:10px;padding:3px 8px">${d.emoji} ${d.grade}</span>
        <span class="hi-time">${d.searched_at.slice(5,16)}</span>
        <button class="btn-del" onclick="delItem(event,'${esc(d.keyword)}')">✕</button>
      </div>
    </div>`;
  }).join('');
}
function reuseKw(kw) {
  document.getElementById('kwInput').value = kw;
  switchTab('search');
  doSearch();
}
async function delItem(e, kw) {
  e.stopPropagation();
  await fetch('/history/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({keyword:kw})});
  loadHistory(); loadGolden();
}
async function clearAll() {
  if (!confirm('히스토리를 전체 삭제할까요?')) return;
  await fetch('/history/clear',{method:'POST'});
  document.getElementById('resultCard').style.display='none';
  loadHistory(); loadGolden();
}

// ── 자동 발굴 ─────────────────────────────────
let selTopic    = '';
let topicLabels = {};
let pollTimer   = null;

async function initTopics() {
  const res = await fetch('/scan/topics');
  topicLabels = await res.json();
  const grid = document.getElementById('topicGrid');
  grid.innerHTML = Object.entries(topicLabels).map(([k,v]) =>
    `<button class="topic-btn" id="tp-${k}" onclick="selTopic2('${k}')">${v}</button>`
  ).join('');
}

function selTopic2(k) {
  selTopic = k;
  document.querySelectorAll('.topic-btn').forEach(b => b.classList.remove('sel'));
  document.getElementById('tp-'+k).classList.add('sel');
  loadScanResults();
}

async function startScan() {
  if (!selTopic) { alert('주제를 먼저 선택해주세요!'); return; }
  const target     = parseInt(document.getElementById('scanTarget').value)||100;
  const min_search = parseInt(document.getElementById('minSlider').value)||1000;
  const comp_ratio = parseFloat(document.getElementById('compRatio').value)||0.5;
  const res = await fetch('/scan/start',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({target, topic:selTopic, min_search, comp_ratio})});
  const d = await res.json();
  if (d.error){alert(d.error);return;}
  document.getElementById('btnStart').disabled = true;
  document.getElementById('btnStop').style.display  = 'inline-block';
  document.getElementById('scanProg').style.display = 'block';
  pollTimer = setInterval(pollScan, 1000);
}

async function stopScan() {
  await fetch('/scan/stop',{method:'POST'});
  clearInterval(pollTimer);
  document.getElementById('btnStart').disabled = false;
  document.getElementById('btnStop').style.display = 'none';
  loadScanResults();
}

async function pollScan() {
  const res = await fetch('/scan/status');
  const d   = await res.json();
  document.getElementById('progPhase').textContent   = d.phase;
  document.getElementById('progBar').style.width     = d.progress+'%';
  document.getElementById('progChecked').textContent = d.checked.toLocaleString();
  document.getElementById('progTotal').textContent   = d.total.toLocaleString();
  document.getElementById('progFound').textContent   = d.found;
  if (d.log && d.log.length)
    document.getElementById('progLog').innerHTML = d.log.map(l=>`<div>${esc(l)}</div>`).join('');
  if (d.results && d.results.length) renderScanItems(d.results, false);
  if (!d.running) {
    clearInterval(pollTimer);
    document.getElementById('btnStart').disabled = false;
    document.getElementById('btnStop').style.display = 'none';
    loadScanResults();
  }
}

async function loadScanResults() {
  if (!selTopic) {
    document.getElementById('scanResultList').innerHTML = '<div class="empty-msg">주제를 선택하면 결과가 표시됩니다</div>';
    document.getElementById('scanResultCount').textContent = '0개';
    return;
  }
  const res  = await fetch('/scan/results?topic='+selTopic);
  const list = await res.json();
  document.getElementById('scanResultCount').textContent = list.length+'개';
  renderScanItems(list, true);
}

function renderScanItems(list, full) {
  const el = document.getElementById('scanResultList');
  if (!list.length) { el.innerHTML='<div class="empty-msg">발굴된 황금키워드가 없습니다</div>'; return; }
  const show = full ? list : list.slice(0,30);
  el.innerHTML = show.map(d => {
    const ratio = d.doc > 0 ? (d.srch/d.doc).toFixed(1) : '∞';
    return `<div class="result-item" onclick="goSearch('${esc(d.keyword)}')">
      <span class="ri-kw">${esc(d.keyword)}</span>
      <div class="ri-stats">
        <span>발행 <b style="color:#dde1ec">${d.doc.toLocaleString()}</b></span>
        <span>검색 <b style="color:var(--gold)">${d.srch.toLocaleString()}</b></span>
        <span>초과 <b style="color:#2ECC71">+${(d.srch-d.doc).toLocaleString()}</b></span>
      </div>
      <span class="ri-ratio">${ratio}×</span>
    </div>`;
  }).join('');
  if (full) document.getElementById('scanResultCount').textContent = list.length+'개';
}

function goSearch(kw) {
  document.getElementById('kwInput').value = kw;
  switchTab('search'); doSearch();
}

async function clearScan() {
  if (!selTopic){alert('주제를 먼저 선택하세요');return;}
  if (!confirm(`[${topicLabels[selTopic]}] 결과를 삭제할까요?`)) return;
  await fetch('/scan/clear',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({topic:selTopic})});
  loadScanResults();
}

function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}

// 초기화
loadHistory(); loadGolden(); initTopics();
</script>
</body></html>"""

@app.route("/")
def index():
    return render_template_string(HTML)

if __name__ == "__main__":
    print("\n" + "━"*50)
    print("  키워드 분석기 시작!")
    print("  http://localhost:5000")
    print("━"*50 + "\n")
    app.run(host="0.0.0.0", debug=False, port=int(os.environ.get("PORT", 5000)))
