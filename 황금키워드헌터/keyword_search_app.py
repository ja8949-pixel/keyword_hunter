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
# 5개 주제별 시드 키워드 (대량 추출 최적화)
# ═══════════════════════════════════════════
TOPICS = {
    "restaurant": {"label": "🍽️ 맛집", "seeds": [
        # 서울 지역별
        "서울맛집추천","강남맛집","홍대맛집","성수동맛집","이태원맛집","건대맛집","종로맛집","신촌맛집",
        "합정맛집","마포맛집","여의도맛집","노량진맛집","구로맛집","강서맛집","잠실맛집","송파맛집",
        "압구정맛집","청담동맛집","서초맛집","사당맛집","방배맛집","신림맛집","관악맛집","동작맛집",
        "노원맛집","도봉맛집","강북맛집","은평맛집","서대문맛집","용산맛집","중구맛집","성동맛집",
        # 수도권
        "인천맛집","수원맛집","성남맛집","분당맛집","용인맛집","고양맛집","일산맛집","파주맛집",
        "김포맛집","광명맛집","안양맛집","부천맛집","안산맛집","시흥맛집","화성맛집","평택맛집",
        "의정부맛집","구리맛집","남양주맛집","하남맛집","양평맛집","가평맛집","포천맛집","연천맛집",
        # 지방 주요도시
        "부산맛집추천","해운대맛집","서면맛집","광안리맛집","남포동맛집","동래맛집","기장맛집",
        "대구맛집","동성로맛집","수성구맛집","경주맛집","울산맛집","포항맛집","창원맛집","진주맛집","통영맛집",
        "대전맛집","청주맛집","천안맛집","공주맛집","부여맛집","서산맛집","태안맛집",
        "광주맛집전라","전주맛집추천","군산맛집","목포맛집","여수맛집","순천맛집","담양맛집",
        "강릉맛집","속초맛집","춘천맛집","원주맛집","강원맛집","평창맛집","양양맛집","삼척맛집",
        # 제주
        "제주맛집추천","제주시맛집","서귀포맛집","중문맛집","애월맛집","협재맛집","성산맛집","한림맛집",
        # 음식 종류별
        "고기집추천","삼겹살맛집","갈비집추천","한우맛집","돼지고기맛집","소고기맛집","양고기맛집",
        "초밥맛집","회맛집","해산물맛집","게요리맛집","랍스터맛집","장어맛집","복어맛집","오마카세추천",
        "라멘맛집","우동맛집","돈카츠맛집","규동맛집","일본음식맛집","스시맛집",
        "파스타맛집","피자맛집","스테이크맛집","브런치맛집","샌드위치맛집","이탈리안맛집","멕시칸맛집",
        "짜장면맛집","짬뽕맛집","마라탕맛집","훠궈맛집","중화요리맛집","딤섬맛집",
        "쌀국수맛집","베트남음식맛집","태국음식맛집","인도음식맛집","동남아음식맛집",
        "국밥맛집","순대국맛집","칼국수맛집","냉면맛집","설렁탕맛집","곰탕맛집","해장국맛집",
        "분식맛집","떡볶이맛집","김밥맛집","순대맛집","어묵맛집","라볶이맛집",
        "찜닭맛집","닭갈비맛집","닭볶음탕맛집","삼계탕맛집","치킨맛집","족발맛집","보쌈맛집",
        "햄버거맛집","수제버거맛집","핫도그맛집","샐러드맛집","비건맛집","채식맛집",
        # 상황별 맛집
        "혼밥맛집","데이트맛집","분위기좋은식당","가족외식맛집","가성비식당","줄서는맛집",
        "숨은맛집","인스타맛집","뷰맛집","야경맛집","루프탑맛집","오션뷰식당",
        "24시간맛집","심야맛집","아이와맛집","반려동물동반맛집","혼밥가능맛집","단체식당추천",
        # 카페·디저트
        "분위기좋은카페","감성카페추천","인스타카페","루프탑카페","뷰카페추천","오션뷰카페",
        "서울카페추천","홍대카페","성수카페","연남동카페","익선동카페","망원동카페","한남동카페","을지로카페",
        "부산카페추천","해운대카페","전주카페","제주카페추천","강릉카페","속초카페추천","춘천카페","경주카페",
        "크로플맛집","케이크맛집","마카롱맛집","빵집추천","소금빵맛집","크루아상맛집","베이글맛집",
        "빙수맛집","팥빙수맛집","디저트맛집추천","파르페맛집","생과일주스맛집",
        "독특한카페","애견카페추천","북카페추천","식물카페","공방카페","갤러리카페","수영장카페",
        "브런치카페","베이커리카페","디저트카페","스페셜티커피","핸드드립카페",
    ]},

    "korean_recipe": {"label": "🍳 한식레시피", "seeds": [
        # 한식 기본 메뉴
        "한식레시피","집밥만들기","찌개레시피","반찬만들기","볶음요리","조림요리","국물요리","무침레시피",
        "된장찌개만들기","김치찌개레시피","순두부찌개","갈비찜레시피","불고기만들기","제육볶음","잡채만들기",
        "떡볶이만들기","비빔밥레시피","삼겹살요리","닭볶음탕","된장국레시피","미역국만들기","콩나물국",
        "도시락반찬","간단반찬","밑반찬만들기","나물무침","김치만들기","에어프라이어한식","솥밥레시피",
        # 한식 심화
        "감자볶음","시금치나물","콩나물무침","계란찜만들기","계란말이","오징어볶음","두부조림","연근조림",
        "멸치볶음","마늘쫑볶음","깻잎김치","파김치","깍두기만들기","열무김치","동치미레시피","백김치만들기",
        "육개장만들기","추어탕만들기","삼계탕만들기","곰탕만들기","설렁탕만들기","부대찌개레시피",
        "짜글이찌개","고추장찌개","돼지찌개","두부찌개","소고기무국","시금치국","근대국","배추된장국",
        "소불고기","돼지불고기","오리불고기","쭈꾸미볶음","낙지볶음","꼴뚜기무침","오삼불고기",
        "갈비구이","LA갈비레시피","등갈비","순살갈비","찜닭만들기","닭강정만들기","닭갈비만들기",
        "삼겹살굽는법","항정살요리","목살요리","수육만들기","보쌈만들기","족발만들기",
        "감자탕만들기","해장국만들기","짬뽕순두부","물만두만들기","군만두만들기","떡국만들기","떡만두국",
        "잡곡밥짓기","곤드레밥만들기","취나물밥","콩밥","팥밥","현미밥","볶음밥만들기","김치볶음밥",
        "아욱국","근대된장국","호박죽만들기","팥죽만들기","전복죽만들기","쇠고기죽만들기",
        "전만들기","동태전","김치전","파전만들기","해물파전","빈대떡만들기","배추전","감자전",
        "강정만들기","잡채만들기","도라지무침","고사리나물","무나물","애호박볶음","가지볶음",
        # 양식
        "파스타만들기","크림파스타","오일파스타","까르보나라","리조또레시피","피자만들기","스테이크굽기",
        "크림스튜","미트볼스파게티","알리오올리오","봉골레파스타","해산물파스타","버섯크림파스타",
        "수제피자도우","나폴레탄피자","마르게리타피자","고르곤졸라피자","스크램블에그","오믈렛만들기",
        "수제버거만들기","치즈버거","연어스테이크","닭가슴살스테이크","등심스테이크","안심스테이크",
        # 중식
        "짜장면만들기","짬뽕만들기","마파두부","깐풍기","탕수육만들기","마라탕만들기","중국식볶음밥",
        "마라샹궈만들기","유린기만들기","새우칠리만들기","꽃빵만들기","만두만들기","딤섬만들기",
        # 일식
        "라멘만들기","우동레시피","돈카츠","오야코동","데리야끼","일본카레","규동만들기","차슈만들기",
        "오니기리만들기","계란말이초밥","연어초밥","참치마요초밥","스시롤","미소국만들기","다시마육수",
        # 다이어트 식단
        "다이어트식단","저칼로리요리","다이어트도시락","간헐적단식식단","키토식단","저탄고지식단",
        "닭가슴살요리","두부다이어트","샐러드만들기","단백질식단","체중감량식단","1200칼로리식단",
        "다이어트간식","클린이팅","다이어트볶음밥","저당식단","당뇨식단","저염식단",
        "두부스테이크","닭가슴살샐러드","오트밀레시피","그릭요거트레시피","고구마요리","달걀다이어트",
        # 베이킹·디저트
        "케이크만들기","쿠키만들기","빵만들기","마카롱만들기","타르트만들기","치즈케이크","롤케이크",
        "파운드케이크","브라우니만들기","머핀만들기","스콘만들기","도넛만들기","크로플만들기",
        "마들렌만들기","와플만들기","팬케이크만들기","식빵만들기","소금빵만들기","시나몬롤",
        "크루아상만들기","베이글만들기","홈베이킹초보","에어프라이어베이킹","글루텐프리빵",
        "무화과타르트","레몬케이크","말차케이크","딸기케이크","초코케이크","당근케이크","바나나케이크",
        # 홈카페·음료
        "홈카페음료","달고나커피만들기","아이스커피만들기","라떼만들기","에이드만들기","스무디만들기",
        "버블티만들기","과일청만들기","레몬에이드","자몽에이드","딸기라떼만들기","말차라떼",
        "콜드브루만들기","드립커피","홈카페레시피","수제청만들기","레몬청만들기","생강청만들기",
        "오트밀크라떼","홈카페도구추천","커피머신추천","모카포트사용법","핸드드립방법","에스프레소만들기",
        # 에어프라이어·간편요리
        "에어프라이어요리","에어프라이어닭갈비","에어프라이어삼겹살","에어프라이어새우","에어프라이어만두",
        "에어프라이어고구마","에어프라이어계란","에어프라이어스테이크","에어프라이어치킨",
        "전자레인지요리","냄비요리","원팬요리","초간단요리","10분요리","혼밥요리","자취요리",
        "캠핑요리레시피","바베큐요리","숯불요리","압력솥요리","찜기요리","솥밥짓기",
    ]},

    "accommodation": {"label": "🏨 숙소", "seeds": [
        # 유형별
        "펜션추천","풀빌라추천","글램핑추천","커플펜션","가족펜션추천","독채펜션추천",
        "한옥스테이","감성숙소추천","오션뷰숙소","오션뷰호텔","수영장펜션","바베큐펜션","온천숙소",
        "반려동물펜션","반려견동반숙소","캠핑장추천","오토캠핑장","카라반캠핑","에어비앤비추천","게스트하우스추천",
        # 경기·수도권
        "가평펜션추천","가평글램핑","가평풀빌라","양평펜션","양평글램핑","포천펜션","연천펜션",
        "강화도숙소","인천펜션","파주숙소","용인글램핑","화성펜션","평택펜션","이천펜션","안성펜션",
        "서울호텔추천","서울게스트하우스","서울호스텔","홍대호텔추천","강남호텔추천","인사동숙소",
        # 강원도
        "강릉펜션추천","강릉숙소추천","강릉풀빌라","강릉오션뷰숙소","강릉독채펜션",
        "속초숙소추천","속초호텔추천","속초오션뷰호텔","속초펜션추천","속초글램핑",
        "양양숙소추천","양양펜션","양양서핑숙소","양양독채펜션","양양풀빌라",
        "춘천숙소","춘천펜션","홍천펜션","홍천글램핑","평창숙소","평창펜션","평창리조트",
        "인제펜션","정선숙소","태백펜션","삼척숙소","삼척오션뷰펜션","동해숙소","원주숙소","영월숙소","횡성숙소",
        # 제주도
        "제주숙소추천","제주펜션추천","제주풀빌라","제주독채펜션","제주감성숙소","제주글램핑",
        "제주시숙소","서귀포숙소","애월숙소","협재숙소","성산숙소","중문숙소","한림숙소","함덕숙소",
        "제주신라호텔","롯데호텔제주","해비치호텔","서귀포칼호텔","제주오션뷰펜션","제주한옥스테이",
        "제주오션스위츠","제주리조트추천","제주감성펜션","제주풀빌라추천","제주가성비숙소",
        # 경상도·남해안
        "부산호텔추천","해운대호텔","광안리숙소","기장펜션","부산오션뷰호텔","부산게스트하우스",
        "거제펜션추천","거제숙소","거제글램핑","거제풀빌라","통영숙소추천","통영펜션","통영게스트하우스",
        "남해펜션","남해숙소","남해독채펜션","남해글램핑","사천숙소","고성숙소","하동숙소","함양숙소",
        "경주숙소추천","경주한옥스테이","경주풀빌라","경주펜션","경주호텔","경주독채숙소",
        # 전라도·여수
        "여수숙소추천","여수펜션추천","여수오션뷰숙소","여수독채펜션","여수풀빌라","여수게스트하우스",
        "순천숙소","목포숙소","완도숙소","고흥숙소","보성숙소","담양숙소","구례숙소","광양숙소","하동숙소",
        "전주한옥스테이","전주숙소추천","전주게스트하우스","군산숙소","익산숙소","남원숙소",
        # 충청도
        "보령해수욕장펜션","태안펜션","서산숙소","홍성숙소","예산숙소","공주숙소","부여숙소","아산온천숙소",
        "단양숙소","제천숙소","충주숙소","청주숙소","수안보온천","문경숙소","괴산숙소",
        # 호텔 유형·브랜드
        "5성급호텔","가성비호텔","조식포함호텔","리조트추천","커플호텔추천","부티크호텔추천","특급호텔추천",
        "신라호텔","롯데호텔","파라다이스호텔","그랜드하얏트","JW메리어트","인터컨티넨탈","조선호텔",
        "앰배서더호텔","노보텔","이비스호텔","힐튼호텔","메리어트호텔","콘래드호텔","포시즌스호텔",
        "호텔뷔페추천","호텔수영장","호텔스파","루프탑바호텔","야경좋은호텔",
        # 글램핑·캠핑
        "글램핑추천","강원도글램핑","경기도글램핑","충청도글램핑","글램핑음식","글램핑준비물","글램핑인테리어",
        "캠핑용품추천","초보캠핑준비","캠핑요리레시피","캠핑장비추천","텐트추천","침낭추천","패딩침낭",
        "캠핑의자추천","캠핑테이블추천","캠핑랜턴추천","캠핑버너추천","캠핑쿨러추천","캠핑수납용품",
        # 해외숙소
        "일본료칸추천","도쿄호텔추천","오사카호텔추천","교토료칸","후쿠오카호텔","오키나와리조트",
        "발리빌라추천","발리숙소추천","태국리조트추천","방콕호텔추천","푸켓리조트","코사무이숙소",
        "하와이호텔추천","괌숙소추천","사이판숙소추천","대만숙소추천","베트남리조트추천","다낭호텔추천",
        "싱가포르호텔추천","홍콩호텔추천","파리호텔추천","로마호텔추천","뉴욕호텔추천","런던호텔추천",
    ]},

    "travel": {"label": "✈️ 여행지", "seeds": [
        # 국내 기본
        "국내여행추천","당일치기여행","1박2일코스","2박3일여행","혼자국내여행","커플국내여행","가족여행국내",
        "서울근교여행","드라이브코스","단풍여행","벚꽃명소여행","야경명소","힐링여행추천","주말여행추천",
        # 강원도
        "강릉여행코스","강릉여행먹거리","속초여행코스","속초여행먹거리","춘천여행","춘천여행코스",
        "양양여행","양양서핑","강원도여행추천","홍천여행","평창여행","정선여행","태백여행",
        "삼척여행","동해여행","영월여행","인제여행","고성여행강원","화천여행","철원여행",
        # 경상도
        "부산여행코스","부산1박2일","부산가볼만한곳","해운대여행","광안리여행","남포동여행","기장여행",
        "경주여행코스","경주볼거리","경주먹거리","경주1박2일","경주2박3일",
        "울산여행","포항여행","영덕여행","울진여행","대구여행","안동여행","영주여행","문경여행",
        "통영여행","남해여행","거제여행코스","사천여행","고성여행경남","하동여행","산청여행","함양여행",
        # 전라도
        "전주여행코스","전주한옥마을","전주먹거리","전주1박2일","군산여행","군산먹거리",
        "여수여행코스","여수먹거리","여수야경","여수1박2일","순천여행","광양여행","담양여행",
        "구례여행","보성여행","목포여행","해남여행","진도여행","완도여행","고흥여행","장성여행",
        "남원여행","임실여행","고창여행","부안여행","변산반도여행","격포여행",
        # 충청도
        "공주여행","부여여행","논산여행","보령여행","태안여행","서산여행","당진여행",
        "천안여행","아산여행","청주여행","충주여행","제천여행","단양여행","옥천여행","영동여행",
        "수안보온천여행","괴산여행","보은여행","문경새재여행","충청도여행추천",
        # 경기·인천·서울
        "가평여행코스","가평1박2일","양평여행","파주여행","강화도여행","인천여행","수원여행",
        "용인여행","화성여행","안성여행","이천여행","남양주여행","양주여행","포천여행","연천여행",
        "서울당일치기","서울가볼만한곳","서울데이트코스","서울야경명소","서울카페거리","서울축제",
        "경복궁","창덕궁","창경궁","덕수궁","북촌한옥마을","인사동여행","광장시장","망원시장",
        # 제주도
        "제주여행코스","제주1박2일","제주2박3일","제주3박4일","제주가볼만한곳","제주혼자여행",
        "제주커플여행","제주가족여행","제주렌트카","제주올레길","제주한달살기","제주여행준비",
        "제주동쪽여행","제주서쪽여행","제주남쪽여행","제주북쪽여행","애월여행","협재여행","함덕여행",
        "성산일출봉","한라산등반","우도여행","마라도여행","비자림","사려니숲길","천지연폭포","정방폭포",
        "제주오름추천","새별오름","성산오름","용눈이오름","다랑쉬오름","제주도노을명소",
        # 계절별 여행
        "봄여행추천","벚꽃여행","봄꽃여행","봄나들이","봄드라이브","봄데이트코스","튤립축제","유채꽃여행",
        "여름여행추천","여름휴가추천","바다여행추천","계곡여행","워터파크추천","여름피서지","해수욕장추천",
        "가을여행추천","단풍명소","억새여행","가을드라이브","가을데이트","단풍시기","은행나무길",
        "겨울여행추천","겨울여행지","눈꽃여행","스키장추천","온천여행","겨울바다여행","빙어낚시",
        # 테마별
        "등산코스추천","트레킹코스","둘레길추천","숲길여행","계곡트레킹","설악산등반","지리산등반","한라산등반",
        "서핑스팟추천","스쿠버다이빙","카약","패들보드","낚시여행","낚시명소","수상레저추천",
        "역사문화여행","박물관추천","미술관추천","사찰여행","고궁여행","전통시장여행","문화유산여행",
        "드라마촬영지","영화촬영지","인스타감성여행","감성사진명소","포토스팟여행",
        "맛집투어여행","먹방여행","시장투어","야시장여행","로컬푸드투어","와이너리투어",
        # 해외여행
        "일본여행코스","오사카여행","도쿄여행코스","교토여행","후쿠오카여행","오키나와여행","홋카이도여행",
        "나고야여행","삿포로여행","도쿄디즈니랜드","유니버설스튜디오재팬","일본온천여행","일본료칸여행",
        "태국여행코스","방콕여행","치앙마이여행","푸켓여행","코사무이여행","파타야여행","아유타야여행",
        "베트남여행","다낭여행코스","호이안여행","하노이여행","호치민여행","하롱베이여행","사파여행","나트랑여행",
        "발리여행코스","싱가포르여행","홍콩여행","대만여행코스","타이베이여행","마카오여행",
        "세부여행","보라카이여행","필리핀여행","코타키나발루여행","쿠알라룸푸르여행","조호르바루여행",
        "유럽여행코스","파리여행","로마여행","바르셀로나여행","런던여행","암스테르담여행",
        "프라하여행","비엔나여행","그리스여행","산토리니여행","터키여행","이스탄불여행","크로아티아여행",
        "스위스여행","포르투갈여행","포르투여행","리스본여행","스페인여행","이탈리아여행","독일여행","체코여행",
        "미국여행코스","뉴욕여행","LA여행","샌프란시스코여행","라스베이거스여행","시카고여행","보스턴여행",
        "하와이여행코스","오아후여행","마우이여행","괌여행코스","사이판여행","팔라우여행","몰디브여행",
        "캐나다여행","밴쿠버여행","토론토여행","호주여행","시드니여행","멜버른여행","뉴질랜드여행","오클랜드여행",
        "두바이여행","아부다비여행","모로코여행","이집트여행","남아공여행","동남아여행추천",
        # 해외여행 준비
        "해외여행준비물","해외여행보험","환전방법","해외로밍방법","여권만들기","비자신청방법",
        "항공권예약방법","저가항공추천","호텔예약사이트","에어비앤비사용법","항공권특가찾는법",
        "여행가방추천","여행용캐리어추천","여행파우치추천","여행용품추천","여행보조배터리추천",
        "여행영어회화","일본어회화여행","태국어회화","베트남어회화","해외여행앱추천",
    ]},

    "etc": {"label": "🌟 기타", "seeds": [
        # 건강·운동
        "헬스초보운동","헬스루틴","스쿼트자세","데드리프트","벤치프레스","홈트운동","맨몸운동",
        "다이어트운동","유산소운동","인터벌트레이닝","체지방감소운동","근육증가운동","PT가격","퍼스널트레이닝",
        "요가초보","요가자세","다이어트요가","필라테스효과","필라테스초보","스트레칭방법","폼롤러사용법",
        "건강검진항목","고혈압관리","당뇨관리","갑상선질환","역류성식도염","허리디스크증상",
        "불면증원인","피부염증상","아토피관리","면역력높이는법","두통원인","어지럼증원인","만성피로원인",
        "종합비타민추천","비타민C효능","비타민D효능","마그네슘효능","오메가3추천","유산균추천",
        "콜라겐효능","홍삼효능","영양제추천","루테인효능","밀크씨슬효능","철분제추천","아연효능",
        # 뷰티·스킨케어
        "스킨케어루틴","기초화장품순서","건성피부관리","지성피부관리","민감성피부케어","선크림추천",
        "수분크림추천","세럼추천","토너추천","앰플추천","마스크팩추천","클렌징폼추천","클렌징오일추천",
        "레티놀효능","나이아신아마이드","여드름케어","모공관리방법","피부장벽강화","각질케어",
        "메이크업순서","파운데이션추천","쿠션팩트추천","립스틱추천","아이섀도우추천","마스카라추천",
        "립틴트추천","컨실러추천","블러셔추천","데일리메이크업","눈썹그리기","네일아트","젤네일추천",
        # 패션·코디
        "여성코디추천","데일리룩","오피스룩","봄코디","여름코디","가을코디","겨울코디",
        "원피스코디","슬랙스코디","청바지코디","스커트코디","블라우스코디","니트코디",
        "코트코디","패딩코디","키작은코디","통통체형코디","여성신발추천","여성가방추천","크로스백추천",
        "남자코디추천","남자데일리룩","남자오피스룩","남자청바지코디","남자니트코디",
        "남자패딩추천","남자스니커즈추천","남자가방추천","남성스킨케어루틴","남자머리스타일",
        # 헤어
        "여자헤어스타일","남자헤어스타일","단발머리","중단발머리","레이어드컷","울프컷","리프컷",
        "셀프염색방법","탈색방법","새치염색","파마추천","볼륨펌","샴푸추천","탈모예방방법",
        "두피케어방법","두피영양제","헤어드라이기추천","고데기추천","트리트먼트추천",
        # 육아·임신
        "임신초기증상","임신준비방법","임산부영양제","태교방법","출산준비물","임신중운동",
        "산후조리원추천","산후다이어트","모유수유방법","신생아돌봄","신생아수면",
        "아기수면교육","이유식시작시기","초기이유식만들기","아기간식추천","분유추천",
        "유아발달","어린이집적응방법","유치원준비물","훈육방법","아이감정코칭",
        "독서교육방법","그림책추천","장난감추천","레고추천","한글공부방법","영어교육유아",
        # 재테크·주식
        "주식투자초보","주식공부방법","ETF투자방법","ETF추천","배당주추천","미국주식투자",
        "S&P500투자","코인투자방법","비트코인투자","금투자방법","ISA계좌","연금저축펀드",
        "아파트청약방법","청약통장만들기","청약가점계산","전세계약방법","주택담보대출",
        "전세사기예방","재개발투자","오피스텔투자","수익형부동산","부동산앱추천","호갱노노",
        "절약방법","가계부쓰는법","짠테크방법","신용카드추천","카드포인트활용","통신비절약",
        "연말정산공제","부업추천","스마트스토어창업","블로그수익","유튜브수익화방법","온라인부업",
        # IT·가전
        "노트북추천","맥북추천","갤럭시북추천","게임노트북추천","학생노트북추천","모니터추천",
        "키보드추천","기계식키보드","무선이어폰추천","노이즈캔슬링이어폰","에어팟추천","갤럭시버즈추천",
        "아이폰추천","갤럭시추천","아이패드추천","갤럭시탭추천","태블릿추천","스마트워치추천",
        "챗GPT활용법","AI앱추천","생성AI도구","업무자동화","생산성앱추천","메모앱추천",
        "냉장고추천","세탁기추천","건조기추천","식기세척기추천","공기청정기추천",
        "청소기추천","로봇청소기추천","에어프라이어추천","전자레인지추천","밥솥추천","인덕션추천",
        # 반려동물
        "강아지품종추천","강아지훈련방법","강아지사료추천","강아지간식추천","강아지건강검진",
        "강아지예방접종","강아지목욕방법","강아지미용","강아지용품추천","강아지동반여행",
        "강아지배변훈련","강아지짖음훈련","강아지분리불안","강아지사회화","강아지중성화",
        "고양이품종추천","고양이사료추천","고양이화장실추천","캣타워추천","고양이건강검진",
        "고양이예방접종","고양이중성화","고양이간식추천","고양이장난감추천","고양이행동의미",
        "고양이구내염","고양이신부전","고양이구토원인","고양이모래추천","고양이습식사료",
        # 인테리어·생활
        "원룸인테리어","신혼집인테리어","거실인테리어","침실인테리어","셀프인테리어방법",
        "이케아추천","다이소인테리어","소파추천","침대추천","조명추천","수납아이디어","커튼추천","러그추천",
        "청소방법","대청소순서","세탁방법","살림꿀팁","정리정돈방법","곰팡이제거방법",
        "베이킹소다활용","구연산활용법","천연세제만들기","옷관리방법","패딩세탁방법","흰옷세탁법",
        # 자기계발·취미
        "자기계발방법","독서습관","아침루틴만들기","영어공부방법","토익공부방법","자격증추천",
        "취업준비방법","이력서쓰는법","자기소개서작성법","면접준비방법","공무원시험준비",
        "그림독학방법","수채화그리기","뜨개질초보","자수배우기","사진촬영기초","기타독학방법",
        "피아노독학","등산초보장비","캠핑초보장비","서핑배우기","낚시입문방법","골프입문",
        "러닝입문","마라톤준비","자전거입문","클라이밍입문","배드민턴레슨","테니스레슨",
        # 기타 트렌드
        "제로웨이스트실천","미니멀라이프","플로깅","비건라이프","채식식단","비건제품추천",
        "재능기부","봉사활동추천","사이드프로젝트","프리랜서방법","재택근무꿀팁","홈오피스구성",
        "독서실추천","스터디카페추천","온라인강의추천","유데미강의추천","클래스101추천",
        "오늘의운세","MBTI유형","혈액형성격","타로카드","힐링방법","멘탈관리방법",
    ]},
}

# ═══════════════════════════════════════════
# 주제별 관련성 필터 (하나라도 포함해야 통과)
# 기타(etc) 는 필터 없음 → 모든 키워드 허용
# ═══════════════════════════════════════════
TOPIC_FILTERS = {
    "restaurant":    ["맛집","식당","음식점","카페","고기집","초밥","라멘","파스타","피자","이자카야","브런치",
                      "디저트","케이크","빵집","소금빵","크로플","마카롱","빙수","와플","햄버거","치킨","족발",
                      "보쌈","찜닭","닭갈비","삼계탕","칼국수","냉면","국밥","순대","떡볶이","짜장","짬뽕",
                      "마라탕","훠궈","쌀국수","오마카세","스테이크","회맛집","해산물","장어"],
    "korean_recipe": ["레시피","만들기","요리법","집밥","찌개","볶음","조림","반찬","김치","나물","무침","구이",
                      "갈비","불고기","잡채","제육","닭볶","비빔","된장","순두부","떡볶이","삼겹","밑반찬",
                      "도시락","한식","에어프라이어","이유식","케이크","쿠키","빵","베이킹","파스타","라멘",
                      "우동","카레","짜장","홈카페","라떼","에이드","스무디","청만들기","커피"],
    "accommodation": ["숙소","펜션","호텔","글램핑","풀빌라","리조트","게스트하우스","료칸","한옥스테이",
                      "독채","캠핑장","오토캠핑","카라반","에어비앤비","숙박","스테이","빌라","민박",
                      "오션뷰","감성숙소","바베큐펜션","수영장펜션","온천숙소","반려동물펜션"],
    "travel":        ["여행","코스","당일치기","1박2일","2박3일","여행지","여행추천","드라이브","나들이",
                      "볼거리","먹거리","관광","투어","명소","핫플","가볼만한","여행코스","힐링","피서",
                      "스키장","서핑","트레킹","등산","사찰","고궁","축제","캠핑","야영","낚시"],
    # "etc" 는 키 없음 → 필터 미적용 (모든 키워드 통과)
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

@app.route("/search/related", methods=["POST"])
def search_related():
    """입력 키워드의 연관 키워드 중 황금/블루오션 키워드를 반환"""
    kw = (request.json or {}).get("keyword", "").strip()
    if not kw:
        return jsonify([])

    # 연관 키워드 수집 (검색어 기준 hint 사용)
    related = get_related([kw])
    if not related:
        return jsonify([])

    # 검색량 0 제거, 검색량 높은 순 정렬
    candidates = sorted(
        [(k, v) for k, v in related.items() if v["total"] >= 100 and k != kw],
        key=lambda x: x[1]["total"], reverse=True
    )[:60]  # 상위 60개만 발행량 조회

    results = []

    def check_related(item):
        rk, sr = item
        doc = get_doc(rk)
        if doc < 0:
            return None
        j = judge(doc, sr["total"])
        # 황금키워드·블루오션·추천 등급만 반환
        if j["g"] in ("황금키워드", "블루오션", "추천"):
            return {
                "keyword":   rk,
                "doc":       doc,
                "srch":      sr["total"],
                "pc":        sr["pc"],
                "mob":       sr["mob"],
                "comp":      round(doc / sr["total"], 2) if sr["total"] else None,
                "grade":     j["g"], "emoji": j["e"], "color": j["c"],
                "ratio":     round(sr["total"] / doc, 1) if doc > 0 else 0,
                "blog_link": f"https://search.naver.com/search.naver?where=blog&query={quote(rk)}",
                "ad_link":   f"https://manage.searchad.naver.com/customers/keywordstool?keywords={quote(rk)}",
            }
        return None

    with ThreadPoolExecutor(max_workers=20) as ex:
        for r in ex.map(check_related, candidates):
            if r:
                results.append(r)

    # 검색량 ÷ 발행량 비율 내림차순 정렬
    results.sort(key=lambda x: x["ratio"], reverse=True)
    return jsonify(results[:30])

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
    # 저장된 과거 데이터에도 관련성 필터 소급 적용 (기타(etc)는 필터 없음)
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
<script src="https://cdn.amplitude.com/script/ffbd47636e66d50380e4e6a37d1dd6ed.js"></script><script>window.amplitude.add(window.sessionReplay.plugin({sampleRate: 1}));window.amplitude.init('ffbd47636e66d50380e4e6a37d1dd6ed', {"fetchRemoteConfig":true,"autocapture":{"attribution":true,"fileDownloads":true,"formInteractions":true,"pageViews":true,"sessions":true,"elementInteractions":true,"networkTracking":true,"webVitals":true,"frustrationInteractions":{"thrashedCursor":true,"errorClicks":true,"deadClicks":true,"rageClicks":true}}});
<title>키워드 분석기</title>
</script>
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

/* 연관 황금키워드 */
.related-section{margin-bottom:20px;display:none}
.related-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
.related-title{font-size:12px;font-weight:700;color:var(--gold);font-family:var(--m);letter-spacing:1px}
.related-sub{font-size:10px;color:var(--mt);font-family:var(--m)}
.related-loading{text-align:center;padding:16px;color:var(--mt);font-family:var(--m);font-size:11px}
.related-list{display:flex;flex-direction:column;gap:5px}
.related-item{background:var(--s1);border-radius:10px;padding:10px 14px;display:flex;align-items:center;gap:10px;cursor:pointer;transition:all .2s;border:1px solid transparent}
.related-item:hover{background:var(--s2)}
.related-kw{font-size:13px;font-weight:700;flex:1}
.related-stats{font-family:var(--m);font-size:10px;color:var(--mt);display:flex;gap:8px;flex-wrap:wrap}
.related-ratio{font-family:var(--m);font-size:11px;font-weight:700;padding:2px 8px;border-radius:12px;white-space:nowrap;border:1px solid}
.related-empty{text-align:center;padding:16px;color:var(--mt);font-family:var(--m);font-size:11px}

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
.topic-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin-bottom:0}
.topic-btn{background:var(--s2);border:1px solid var(--bd);color:var(--mt);padding:10px 6px;border-radius:9px;font-family:var(--f);font-size:12px;font-weight:700;cursor:pointer;transition:all .2s;text-align:center;line-height:1.4}
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

  <!-- 연관 황금키워드 -->
  <div class="related-section" id="relatedSection">
    <div class="related-header">
      <span class="related-title">🔗 연관 황금키워드 추천</span>
      <span class="related-sub" id="relatedSub">연관 키워드 분석 중...</span>
    </div>
    <div class="related-list" id="relatedList">
      <div class="related-loading"><span class="spinner"></span>연관 키워드 황금 분석 중...</div>
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
  // 연관 섹션 초기화
  const relSec = document.getElementById('relatedSection');
  relSec.style.display = 'none';
  document.getElementById('relatedList').innerHTML = '<div class="related-loading"><span class="spinner"></span>연관 키워드 황금 분석 중...</div>';
  document.getElementById('relatedSub').textContent = '연관 키워드 분석 중...';
  try {
    const res = await fetch('/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({keyword:kw})});
    const d = await res.json();
    if (d.error){alert(d.error);return;}
    showResult(d); loadHistory(); loadGolden();
    // 연관 황금키워드 섹션 표시 후 비동기 로드
    relSec.style.display = 'block';
    loadRelated(kw);
  } catch(e){alert('오류: '+e.message);}
  finally{
    document.getElementById('searchBtn').disabled = false;
    document.getElementById('loading').style.display = 'none';
  }
}

// ── 연관 황금키워드 ─────────────────────────
async function loadRelated(kw) {
  try {
    const res = await fetch('/search/related',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({keyword:kw})});
    const list = await res.json();
    const el = document.getElementById('relatedList');
    const sub = document.getElementById('relatedSub');
    if (!list.length) {
      sub.textContent = '황금 연관키워드 없음';
      el.innerHTML = '<div class="related-empty">조건에 맞는 연관 황금키워드가 없습니다</div>';
      return;
    }
    sub.textContent = `${list.length}개 발견`;
    el.innerHTML = list.map(d => {
      const ratioTxt = d.ratio >= 1 ? d.ratio.toFixed(1)+'×' : (d.ratio*100).toFixed(0)+'%';
      const borderClr = d.color+'55';
      return `<div class="related-item" onclick="reuseKw('${esc(d.keyword)}')" style="border-color:${borderClr}">
        <span class="related-kw" style="color:${d.color}">${esc(d.emoji)} ${esc(d.keyword)}</span>
        <div class="related-stats">
          <span>발행 <b style="color:#dde1ec">${d.doc.toLocaleString()}</b></span>
          <span>검색 <b style="color:var(--gold)">${d.srch.toLocaleString()}</b></span>
          <span style="display:none" class="mob-hide">PC ${d.pc.toLocaleString()} / 모바일 ${d.mob.toLocaleString()}</span>
        </div>
        <div style="display:flex;align-items:center;gap:6px">
          <span class="related-ratio" style="color:${d.color};border-color:${borderClr};background:${d.color}12">${ratioTxt}</span>
          <a href="${d.blog_link}" target="_blank" onclick="event.stopPropagation()" style="font-family:var(--m);font-size:9px;color:var(--mt);text-decoration:none;padding:2px 7px;border:1px solid var(--bd);border-radius:4px" title="블로그검색">↗</a>
        </div>
      </div>`;
    }).join('');
  } catch(e) {
    document.getElementById('relatedSub').textContent = '분석 실패';
    document.getElementById('relatedList').innerHTML = '<div class="related-empty">연관 키워드 분석 중 오류가 발생했습니다</div>';
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
