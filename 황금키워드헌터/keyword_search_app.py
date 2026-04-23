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

GOLD_MAX_DOCS  = 10000   # 황금키워드 발행량 상한 (완화)
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
# 대분류 카테고리 시드 키워드
# ═══════════════════════════════════════════
TOPICS = {
    "food_cafe": {"label": "🍽️ 맛집/카페", "seeds": [
        # ── 고기류 ──
        "삼겹살","삼겹살집","항정살","목살","갈비","갈비집","한우","소고기","돼지고기","양갈비","등갈비",
        "돼지갈비","LA갈비","우대갈비","갈비탕","갈비찜","불고기","제육볶음","수육","보쌈","족발",
        "흑돼지","흑돼지구이","양념갈비","생갈비","정육식당","고기뷔페","무한리필고기",
        # ── 해산물·해물 ──
        "회","횟집","해산물","초밥","오마카세","스시","장어구이","민물장어","꽃게찜","킹크랩","랍스터",
        "해물탕","해물찜","게장","간장게장","양념게장","굴","굴요리","낙지볶음","쭈꾸미볶음","문어숙회",
        "복어","복국","생선구이","조개구이","전복죽","성게비빔밥","물회","가자미회",
        # ── 닭·오리 ──
        "찜닭","닭갈비","닭볶음탕","닭발","치킨","후라이드치킨","양념치킨","순살치킨","오리주물럭",
        "오리고기","삼계탕","닭한마리","닭도리탕","닭칼국수","닭죽",
        # ── 국물요리·탕류 ──
        "국밥","순대국","돼지국밥","감자탕","해장국","설렁탕","곰탕","삼계탕","추어탕","청국장",
        "된장찌개","김치찌개","부대찌개","순두부찌개","짬뽕","짬뽕국물","갈비탕","꼬리곰탕","우족탕",
        "육개장","뚝배기불고기","황태국","콩나물국",
        # ── 면류 ──
        "냉면","평양냉면","물냉면","비빔냉면","막국수","칼국수","수제비","짜장면","짬뽕","우동",
        "라멘","일본라멘","하카타라멘","쇼유라멘","미소라멘","돈코츠라멘","파스타","크림파스타",
        "까르보나라","알리오올리오","봉골레","베트남쌀국수","쌀국수","쌀국수집","막국수집",
        # ── 분식·길거리음식 ──
        "떡볶이","로제떡볶이","크림떡볶이","순대","튀김","어묵","김밥","충무김밥","핫도그",
        "타코야키","붕어빵","호떡","계란빵","와플","크레이프",
        # ── 중식 ──
        "마라탕","마라샹궈","훠궈","중국집","짬뽕집","딤섬","탕수육","깐풍기","유린기","마파두부",
        "마라맛","사천요리","홍콩음식","대만음식","중화요리",
        # ── 일식 ──
        "이자카야","일본식선술집","돈카츠","카츠동","오야코동","규동","텐동","오니기리","타코야키",
        "야키토리","사케","일본술","일본요리","일식","일본가정식",
        # ── 양식 ──
        "스테이크","립아이","티본스테이크","안심스테이크","등심스테이크","함박스테이크","스테이크집",
        "버거","수제버거","스매시버거","치즈버거","브런치","에그베네딕트","팬케이크","브런치카페",
        "파스타집","이탈리안","이탈리아요리","피자","피자집","나폴리피자","화덕피자",
        # ── 동남아·기타 ──
        "베트남음식","태국음식","쏨땀","팟타이","그린카레","커리","인도커리","인도음식",
        "멕시칸","부리토","타코","케밥","중동음식","터키음식","하와이안포케",
        # ── 채식·건강식 ──
        "비건식당","채식식당","비건버거","두부요리","샐러드바","샐러드전문점","글루텐프리",
        "저칼로리음식","다이어트식당","건강식","로푸드",
        # ── 뷔페·무한리필 ──
        "뷔페","호텔뷔페","샐러드뷔페","고기뷔페","초밥뷔페","해산물뷔페","무한리필","런치뷔페",
        "조식뷔페","브런치뷔페","파인다이닝",
        # ── 상황·분위기별 ──
        "혼밥","혼밥식당","혼밥가능","혼밥메뉴","데이트식당","데이트코스음식","분위기좋은식당",
        "단체회식","회식장소","가족외식","아이와외식","룸식당","프라이빗다이닝",
        "야외식당","루프탑식당","한강뷰식당","오션뷰식당","뷰맛집","야경식당",
        "새벽식당","24시간식당","심야식당","해장음식","해장국집",
        "가성비식당","저렴한식당","줄서는식당","예약필수식당","오픈런식당","핫플레이스식당",
        # ── 지역별 음식 특산 ──
        "전주비빔밥","광주상추튀김","부산밀면","대구막창","제주흑돼지","경주빵","통영굴","여수갈치조림",
        "춘천닭갈비","강릉초당순두부","속초닭강정","안동찜닭","진주냉면","남해멸치쌈밥",
        # ── 카페·음료 ──
        "카페","카페추천","감성카페","분위기카페","인스타카페","뷰카페","루프탑카페","정원카페",
        "한옥카페","독채카페","독립카페","로스터리카페","스페셜티카페","핸드드립","콜드브루",
        "플랫화이트","아인슈페너","달고나커피","흑당라떼","말차라떼","딸기라떼","복숭아아이스티",
        "에이드","레몬에이드","자몽에이드","자두에이드","스무디","쉐이크","버블티","타피오카",
        "서울카페","강남카페","홍대카페","성수카페","연남동카페","망원동카페","익선동카페",
        "을지로카페","한남동카페","이태원카페","압구정카페","여의도카페","신사동카페",
        "부산카페","해운대카페","광안리카페","제주카페","애월카페","협재카페","함덕카페",
        "강릉카페","속초카페","경주카페","전주카페","여수카페","통영카페","남해카페",
        # ── 베이커리·디저트 ──
        "베이커리","빵집","소금빵","크루아상","베이글","식빵","바게트","치아바타","도넛",
        "크로플","와플","마카롱","케이크","디저트","조각케이크","케이크맛집",
        "팥빙수","빙수","망고빙수","딸기빙수","눈꽃빙수","소프트아이스크림","젤라또",
        "타르트","에그타르트","파운드케이크","롤케이크","치즈케이크","티라미수",
        "크레이프","팬케이크","아이스크림","소프트크림","소프트아이스크림",
        # ── 음료·티 ──
        "티카페","제로티","허브차","캐모마일","얼그레이","로이보스","오미자차","유자차","녹차",
        "커피","아메리카노","카페라떼","카푸치노","에스프레소","바닐라라떼","카라멜마키아토",
        # ── 편의·접근성 ──
        "24시간카페","공부카페","노트북카페","스터디카페","애견카페","북카페","보드게임카페",
        "독서실카페","코인노래방카페","방탈출카페","인형뽑기카페",
    ]},

    "travel_stay": {"label": "✈️ 여행/숙박", "seeds": [
        "국내여행추천","당일치기여행","1박2일코스","2박3일여행","주말여행추천","드라이브코스","힐링여행추천",
        "강릉여행코스","속초여행코스","양양여행","춘천여행","제주여행코스","제주1박2일","제주가볼만한곳",
        "부산여행코스","부산1박2일","경주여행코스","전주여행코스","여수여행코스","담양여행","통영여행",
        "가평여행코스","양평여행","파주여행","강화도여행","서울데이트코스","서울가볼만한곳",
        "봄여행추천","벚꽃여행","여름여행추천","계곡여행","가을여행추천","단풍명소","겨울여행추천","눈꽃여행",
        "일본여행코스","오사카여행","도쿄여행코스","교토여행","후쿠오카여행","오키나와여행","홋카이도여행",
        "태국여행코스","방콕여행","치앙마이여행","푸켓여행","베트남여행","다낭여행코스","하노이여행",
        "발리여행코스","싱가포르여행","대만여행코스","유럽여행코스","파리여행","로마여행","스위스여행",
        "하와이여행코스","괌여행코스","사이판여행","몰디브여행","해외여행준비물","항공권예약방법","환전방법",
        "펜션추천","풀빌라추천","글램핑추천","커플펜션","독채펜션추천","한옥스테이","감성숙소추천",
        "오션뷰숙소","수영장펜션","반려동물펜션","캠핑장추천","오토캠핑장","글램핑음식","캠핑용품추천",
        "가평펜션추천","가평글램핑","강릉펜션추천","속초숙소추천","양양펜션","제주숙소추천","제주풀빌라",
        "부산호텔추천","해운대호텔","경주숙소추천","경주한옥스테이","여수숙소추천","전주한옥스테이",
        "5성급호텔","가성비호텔","조식포함호텔","리조트추천","일본료칸추천","발리빌라추천","다낭호텔추천",
    ]},

    "fashion_beauty": {"label": "👗 패션/뷰티", "seeds": [
        "여성코디추천","데일리룩","오피스룩","봄코디","여름코디","가을코디","겨울코디",
        "원피스코디","슬랙스코디","청바지코디","스커트코디","니트코디","코트코디","패딩코디",
        "키작은코디","통통체형코디","여성신발추천","여성가방추천","크로스백추천",
        "남자코디추천","남자데일리룩","남자청바지코디","남자니트코디","남자패딩추천","남자스니커즈추천",
        "스킨케어루틴","기초화장품순서","건성피부관리","지성피부관리","민감성피부케어","선크림추천",
        "수분크림추천","세럼추천","토너추천","앰플추천","마스크팩추천","클렌징폼추천","클렌징오일추천",
        "레티놀효능","나이아신아마이드","여드름케어","모공관리방법","피부장벽강화","각질케어",
        "메이크업순서","파운데이션추천","쿠션팩트추천","립스틱추천","아이섀도우추천","마스카라추천",
        "립틴트추천","컨실러추천","블러셔추천","데일리메이크업","눈썹그리기","네일아트","젤네일추천",
        "여자헤어스타일","남자헤어스타일","단발머리","레이어드컷","울프컷","셀프염색방법","탈색방법",
        "파마추천","볼륨펌","샴푸추천","탈모예방방법","두피케어방법","헤어드라이기추천","고데기추천",
    ]},

    "sports_exercise": {"label": "💪 스포츠/운동", "seeds": [
        "헬스초보운동","헬스루틴","스쿼트자세","데드리프트","벤치프레스","홈트운동","맨몸운동",
        "다이어트운동","유산소운동","인터벌트레이닝","체지방감소운동","근육증가운동","PT가격","퍼스널트레이닝",
        "요가초보","요가자세","다이어트요가","필라테스효과","필라테스초보","스트레칭방법","폼롤러사용법",
        "러닝입문","마라톤준비","자전거입문","클라이밍입문","배드민턴레슨","테니스레슨","골프입문",
        "등산코스추천","트레킹코스","둘레길추천","설악산등반","지리산등반","한라산등반",
        "서핑배우기","스쿠버다이빙","카약","패들보드","낚시입문방법","수상레저추천",
        "스키장추천","보드복추천","스키복추천","스키장비추천","수영강습","수영자세","수영복추천",
        "크로스핏","케틀벨운동","밴드운동","TRX운동","폼롤러스트레칭","근막이완","부상예방운동",
    ]},

    "performance_exhibit": {"label": "🎭 공연/전시", "seeds": [
        "뮤지컬추천","뮤지컬티켓","뮤지컬후기","뮤지컬라이온킹","뮤지컬레미제라블","뮤지컬맘마미아",
        "뮤지컬오페라의유령","뮤지컬위키드","뮤지컬킹키부츠","연극추천","연극티켓","소극장연극",
        "전시회추천","서울전시회","미술관추천","국립중앙박물관","국립현대미술관","리움미술관",
        "사진전시회","팝업스토어추천","갤러리추천","아트페어","서울아트페어",
        "콘서트추천","콘서트티켓","아이돌콘서트","팬미팅","단독콘서트",
        "클래식공연","오케스트라공연","발레공연","오페라공연","재즈공연","뮤직페스티벌",
        "축제추천","지역축제","봄축제","여름축제","불꽃축제","빛축제","미디어아트전시",
    ]},

    "pets": {"label": "🐾 반려동물", "seeds": [
        "강아지품종추천","강아지훈련방법","강아지사료추천","강아지간식추천","강아지건강검진",
        "강아지예방접종","강아지목욕방법","강아지미용","강아지용품추천","강아지동반여행",
        "강아지배변훈련","강아지짖음훈련","강아지분리불안","강아지사회화","강아지중성화",
        "강아지피부병","강아지슬개골","강아지심장사상충","강아지구토원인","강아지설사원인",
        "고양이품종추천","고양이사료추천","고양이화장실추천","캣타워추천","고양이건강검진",
        "고양이예방접종","고양이중성화","고양이간식추천","고양이장난감추천","고양이행동의미",
        "고양이구내염","고양이신부전","고양이구토원인","고양이모래추천","고양이습식사료",
        "반려동물보험","펫보험추천","동물병원추천","반려동물용품추천","반려견유치원","펫호텔추천",
    ]},

    "game": {"label": "🎮 게임", "seeds": [
        "롤챔피언추천","롤티어올리기","롤원딜챔피언","롤탑챔피언","롤정글챔피언","롤미드챔피언","롤서포터",
        "배틀그라운드설정","배틀그라운드공략","오버워치영웅추천","오버워치공략","발로란트공략",
        "스타크래프트","디아블로4","로스트아크직업","로스트아크공략","메이플스토리보스공략",
        "원신공략","원신캐릭터추천","붕괴스타레일","명일방주덱추천","아이돌마스터",
        "닌텐도스위치게임추천","포켓몬추천","젤다의전설","마리오카트","슈퍼마리오오디세이",
        "PS5게임추천","엑스박스게임추천","PC게임추천","인디게임추천","스팀게임추천",
        "게임핵심공략","게임마우스추천","게이밍키보드추천","게이밍모니터추천","게이밍헤드셋추천",
        "스트리머추천","게임방송","트위치스트리머","유튜브게임채널","e스포츠","롤드컵","오버워치리그",
    ]},

    "it_tech": {"label": "💻 IT/테크", "seeds": [
        "노트북추천","맥북추천","갤럭시북추천","게임노트북추천","학생노트북추천","모니터추천",
        "키보드추천","기계식키보드","무선이어폰추천","노이즈캔슬링이어폰","에어팟추천","갤럭시버즈추천",
        "아이폰추천","갤럭시추천","아이패드추천","갤럭시탭추천","태블릿추천","스마트워치추천",
        "챗GPT활용법","AI앱추천","생성AI도구","업무자동화","생산성앱추천","메모앱추천","노션활용법",
        "냉장고추천","세탁기추천","건조기추천","식기세척기추천","공기청정기추천","로봇청소기추천",
        "에어프라이어추천","인덕션추천","밥솥추천","청소기추천","가습기추천","제습기추천",
        "스마트홈구성","홈IoT추천","NAS추천","공유기추천","VPN추천","클라우드저장소추천",
        "파이썬독학","코딩독학","앱개발입문","웹개발독학","유튜브채널운영","블로그SEO","스마트스토어창업",
    ]},

    "economy_biz": {"label": "💰 경제/비즈니스/부동산", "seeds": [
        "주식투자초보","주식공부방법","ETF투자방법","ETF추천","배당주추천","미국주식투자",
        "S&P500투자","코인투자방법","비트코인투자","금투자방법","ISA계좌","연금저축펀드",
        "아파트청약방법","청약통장만들기","청약가점계산","전세계약방법","주택담보대출",
        "전세사기예방","재개발투자","오피스텔투자","수익형부동산","부동산앱추천","호갱노노",
        "절약방법","가계부쓰는법","짠테크방법","신용카드추천","카드포인트활용","통신비절약",
        "연말정산공제","부업추천","스마트스토어창업","블로그수익","유튜브수익화방법","온라인부업",
        "프리랜서방법","재택근무꿀팁","사이드프로젝트","직장인재테크","월급관리방법","적금추천",
        "창업아이템","소자본창업","무인창업","카페창업비용","식당창업","배달창업","프랜차이즈추천",
    ]},

    "education": {"label": "📚 교육/학문", "seeds": [
        "영어공부방법","토익공부방법","토스공부방법","오픽공부방법","영어회화독학","영어단어암기법",
        "수학공부방법","과학공부방법","국어공부방법","사회공부방법","역사공부방법",
        "자격증추천","컴퓨터활용능력","한국사능력검정","ITQ자격증","정보처리기사","공인중개사시험",
        "취업준비방법","이력서쓰는법","자기소개서작성법","면접준비방법","공무원시험준비",
        "수능공부방법","수능국어공부","수능수학공부","수능영어공부","인서울대학교","의대공부방법",
        "독서습관","아침루틴만들기","자기계발방법","온라인강의추천","유데미강의추천","클래스101추천",
        "유아영어교육","어린이영어","초등수학","중학수학","고등수학","한글공부방법","독서교육방법",
        "임용고시","교원자격증","사회복지사자격증","간호사국가시험","약사국가시험","의사국가시험",
    ]},

    "health_medical": {"label": "🏥 건강/의학", "seeds": [
        "건강검진항목","고혈압관리","당뇨관리","갑상선질환","역류성식도염","허리디스크증상",
        "불면증원인","피부염증상","아토피관리","면역력높이는법","두통원인","어지럼증원인","만성피로원인",
        "종합비타민추천","비타민C효능","비타민D효능","마그네슘효능","오메가3추천","유산균추천",
        "콜라겐효능","홍삼효능","영양제추천","루테인효능","밀크씨슬효능","철분제추천","아연효능",
        "다이어트식단","저칼로리요리","다이어트도시락","간헐적단식식단","키토식단","닭가슴살요리",
        "임신초기증상","임신준비방법","임산부영양제","출산준비물","산후조리원추천","산후다이어트",
        "신생아돌봄","이유식시작시기","초기이유식만들기","분유추천","아기간식추천",
        "갱년기증상","갱년기영양제","전립선건강","남성호르몬","여성호르몬","골다공증예방",
        "치아관리방법","임플란트비용","충치예방","라식라섹비용","눈건강","눈영양제",
    ]},

    "entertainment": {"label": "🎬 엔터(도서/영화/드라마/음악/사진영상)", "seeds": [
        "소설추천","베스트셀러책추천","자기계발책추천","인문학책추천","에세이추천","책추천2024",
        "영화추천","넷플릭스영화추천","공포영화추천","로맨스영화추천","액션영화추천","SF영화추천",
        "한국영화추천","외국영화추천","CGV상영중","넷플릭스드라마추천","왓챠드라마추천",
        "한국드라마추천","미국드라마추천","일본드라마추천","중국드라마추천","웹드라마추천",
        "넷플릭스시리즈추천","디즈니플러스추천","애플TV추천","티빙드라마추천","웨이브드라마추천",
        "아이돌추천","케이팝추천","신보추천","음악추천","플레이리스트추천","재즈음악추천","팝송추천",
        "유튜브채널추천","팟캐스트추천","인디음악추천","OST추천","발라드추천","힙합추천","R&B추천",
        "카메라추천","미러리스카메라추천","DSLR추천","유튜브카메라추천","사진구도잡는법",
        "라이트룸편집","포토샵독학","영상편집독학","프리미어프로","유튜브영상편집","릴스편집",
        "웹툰추천","만화추천","애니메이션추천","게임OST추천","버추얼유튜버","스트리머추천",
    ]},

    "daily_etc": {"label": "🌟 기타(일상/리뷰/인테리어/정보)", "seeds": [
        "원룸인테리어","신혼집인테리어","거실인테리어","침실인테리어","셀프인테리어방법",
        "이케아추천","다이소인테리어","소파추천","침대추천","조명추천","수납아이디어","커튼추천","러그추천",
        "청소방법","대청소순서","세탁방법","살림꿀팁","정리정돈방법","곰팡이제거방법",
        "베이킹소다활용","구연산활용법","옷관리방법","패딩세탁방법","흰옷세탁법",
        "DIY인테리어","셀프페인팅","원목가구DIY","조명DIY","선반DIY","페이크그린인테리어",
        "일상브이로그","주부일상","직장인일상","자취일상","육아일상","워킹맘일상",
        "상품리뷰","쿠팡추천","다이소추천","올리브영추천","아이허브추천","해외직구추천",
        "정보공유","생활꿀팁","알뜰살뜰","절약꿀팁","혜택정보","이벤트정보",
        "MBTI유형","오늘의운세","타로카드","힐링방법","멘탈관리방법","긍정마인드",
        "제로웨이스트실천","미니멀라이프","비건라이프","환경보호실천","플로깅",
        "임신준비방법","임산부일상","육아템추천","아이와가볼만한곳","어린이놀이터추천","키즈카페추천",
    ]},
}

# ═══════════════════════════════════════════
# 주제별 관련성 필터 (하나라도 포함해야 통과)
# 필터 없는 카테고리는 모든 키워드 허용
# ═══════════════════════════════════════════
TOPIC_FILTERS = {
    # food_cafe: 필터 없음 → 음식·카페 관련 모든 키워드 통과 (시드 자체로 방향 제어)

    "travel_stay":       ["여행","코스","당일치기","1박2일","2박3일","여행지","드라이브","나들이",
                          "볼거리","먹거리","관광","투어","명소","가볼만한","힐링","피서","펜션","숙소",
                          "호텔","글램핑","풀빌라","리조트","료칸","한옥스테이","독채","캠핑장","오토캠핑",
                          "숙박","스테이","오션뷰","감성숙소","항공권","여행준비"],
    "fashion_beauty":    ["코디","룩","패션","스타일","옷","청바지","원피스","코트","패딩","니트","슬랙스",
                          "스킨케어","화장품","선크림","세럼","토너","앰플","마스크팩","클렌징","레티놀",
                          "메이크업","파운데이션","립스틱","아이섀도우","마스카라","립틴트","컨실러",
                          "헤어","샴푸","탈모","파마","염색","드라이기","고데기","네일","젤네일"],
    "sports_exercise":   ["운동","헬스","스쿼트","데드리프트","벤치프레스","홈트","맨몸운동","유산소",
                          "요가","필라테스","스트레칭","러닝","마라톤","자전거","클라이밍","배드민턴",
                          "테니스","골프","등산","트레킹","서핑","스쿠버","카약","낚시","스키","스노보드",
                          "수영","크로스핏","케틀벨","PT","퍼스널트레이닝"],
    "performance_exhibit":["뮤지컬","연극","전시","공연","콘서트","갤러리","미술관","박물관","팝업스토어",
                           "클래식","발레","오페라","재즈","페스티벌","축제","오케스트라","아트페어",
                           "티켓","좌석","후기","관람"],
    "pets":              ["강아지","고양이","반려","펫","애견","애묘","사료","간식","용품","훈련","미용",
                          "예방접종","건강검진","중성화","산책","동물병원","펫보험","캣타워","화장실","모래"],
    "game":              ["게임","롤","배그","오버워치","발로란트","스타크래프트","디아블로","로스트아크",
                          "메이플","원신","닌텐도","포켓몬","PS5","스팀","인디게임","공략","챔피언","직업",
                          "스트리머","e스포츠","게이밍","마우스","키보드","헤드셋","모니터"],
    "it_tech":           ["노트북","맥북","모니터","키보드","이어폰","에어팟","아이폰","갤럭시","아이패드",
                          "태블릿","스마트워치","챗GPT","AI","생성AI","자동화","생산성","앱","냉장고",
                          "세탁기","건조기","공기청정기","로봇청소기","에어프라이어","인덕션","스마트홈","IoT",
                          "코딩","파이썬","개발","프로그래밍","SEO","블로그"],
    "economy_biz":       ["주식","ETF","투자","코인","비트코인","금투자","ISA","연금","펀드","청약","부동산",
                          "전세","월세","아파트","오피스텔","대출","담보","재테크","절약","가계부","신용카드",
                          "부업","창업","스마트스토어","수익화","프리랜서","재택","사이드프로젝트"],
    "education":         ["공부방법","학습","독학","자격증","토익","토스","오픽","영어","수학","과학",
                          "취업","이력서","자기소개서","면접","공무원","수능","임용","대학","강의","온라인강의",
                          "유아교육","어린이","초등","중학","고등","한글","독서교육","국어","역사"],
    "health_medical":    ["건강","검진","고혈압","당뇨","갑상선","역류성","디스크","불면증","아토피","면역",
                          "비타민","마그네슘","오메가","유산균","콜라겐","홍삼","영양제","루테인","철분",
                          "다이어트","칼로리","단식","키토","임신","임산부","출산","산후","이유식","분유",
                          "갱년기","전립선","치아","임플란트","라식","라섹","눈건강"],
    # "entertainment", "daily_etc" 는 필터 없음 → 모든 키워드 통과
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

# ═══════════════════════════════════════════
# 수식어 사전 (파생어 대량 생성용)
# ═══════════════════════════════════════════
MODIFIERS = {
    "intent":    ["추천","후기","리뷰","비교","가격","비용","얼마","방법","하는법","순위","종류","장단점","효과","솔직한","정리"],
    "time":      ["2025","요즘","최근","최신","신상","트렌드","요즘핫한"],
    "situation": ["혼자","커플","가족","주말","데이트","초보","입문","직장인","20대","30대","40대"],
    "purchase":  ["구매","어디서","싼","저렴한","가성비","할인","쿠폰","최저가"],
    "location":  ["서울","부산","제주","강남","홍대","수도권","경기","인천"],
}

# 카테고리별 우선 수식어 (카테고리 특성에 맞게 조합 최적화)
CATEGORY_MODIFIERS = {
    "food_cafe":          ["추천","후기","가격","혼자","커플","주말","데이트","가성비","맛집","유명한",
                           "줄서는","예약","오픈런","분위기","웨이팅","숨은","근처","동네","새로생긴","인기"],
    "travel_stay":        ["코스","추천","후기","혼자","커플","가족","주말","2025","1박2일","당일치기"],
    "fashion_beauty":     ["추천","후기","가격","사용법","효과","2025","요즘","순위","비교","살때"],
    "sports_exercise":    ["추천","효과","방법","초보","입문","하는법","루틴","순서","후기","비용"],
    "performance_exhibit":["추천","후기","2025","커플","데이트","예매","가격","순위","관람"],
    "pets":               ["추천","방법","가격","증상","원인","효과","후기","사료","용품","비교"],
    "game":               ["공략","추천","방법","하는법","후기","순위","2025","직업","캐릭터"],
    "it_tech":            ["추천","비교","가격","후기","사용법","순위","2025","최신","비교분석"],
    "economy_biz":        ["방법","추천","후기","비교","2025","초보","절약","수익","투자"],
    "education":          ["방법","추천","후기","후기","비교","2025","초보","독학","공부법"],
    "health_medical":     ["증상","원인","방법","효과","추천","비교","2025","부작용","주의사항"],
    "entertainment":      ["추천","후기","2025","순위","리뷰","요즘","최신","인기","감상"],
    "daily_etc":          ["추천","후기","방법","가격","2025","요즘","비교","리뷰","꿀팁"],
}

# 시즌 키워드 → 해당 월에만 가중치 부여
SEASONAL_MAP = {
    "봄":([3,4,5],1.4),  "벚꽃":([3,4],1.5),    "봄나들이":([3,4,5],1.4),
    "여름":([6,7,8],1.4),"휴가":([7,8],1.5),     "바다":([6,7,8,9],1.3),
    "피서":([7,8],1.5),  "계곡":([6,7,8],1.4),   "워터파크":([6,7,8],1.4),
    "가을":([9,10,11],1.4),"단풍":([10,11],1.5), "억새":([10,11],1.4),
    "겨울":([12,1,2],1.3),"크리스마스":([12],1.6),"눈썰매":([12,1,2],1.5),
    "스키":([12,1,2],1.5),"온천":([11,12,1,2],1.3),
    "설날":([1,2],1.5),  "추석":([9,10],1.5),    "수능":([10,11],1.5),
    "입학":([2,3],1.4),  "졸업":([1,2],1.4),     "어버이날":([5],1.4),
}

# 실시간성 키워드 패턴 (시점/유행 신호)
REALTIME_PATTERNS = [
    "요즘","최근","최신","트렌드","인기","급상승","핫한","뜨는","유행","2025",
    "신상","새로운","요즘뜨는","요즘핫","레트로","역주행","화제",
]

# 구매 의도 계수
PURCHASE_HIGH = ["구매","가격","비용","얼마","할인","쿠폰","최저가","어디서","살수있","싼","저렴"]
PURCHASE_MID  = ["후기","리뷰","비교","추천","순위","좋은","인기","장단점"]

def expand_seeds_with_modifiers(seeds, topic_key, max_extra=150):
    """시드 키워드 + 수식어 조합으로 파생 시드 대량 생성"""
    mods = CATEGORY_MODIFIERS.get(topic_key, MODIFIERS["intent"][:8])
    seen = set(seeds)
    extras = []
    # 시드 앞 30개만 조합 (대표 시드)
    for seed in seeds[:30]:
        for mod in mods:
            derived = seed + mod
            if derived not in seen:
                seen.add(derived)
                extras.append(derived)
            if len(extras) >= max_extra:
                break
        if len(extras) >= max_extra:
            break
    return extras

def seasonal_bonus(kw):
    """현재 월 기준 시즌 가중치 (시즌 키워드면 상승, 비시즌이면 하락)"""
    month = datetime.now().month
    for keyword, (months, weight) in SEASONAL_MAP.items():
        if keyword in kw:
            return weight if month in months else 0.75
    return 1.0

def purchase_intent_coef(kw):
    """구매 의도 계수: 높은 의도 1.4 / 중간 1.2 / 일반 1.0"""
    if any(p in kw for p in PURCHASE_HIGH):
        return 1.4
    if any(p in kw for p in PURCHASE_MID):
        return 1.2
    return 1.0

def realtime_score(pc, mob, kw):
    """실시간성 점수 = 모바일 비중 × 시즌 × 키워드 패턴"""
    total = pc + mob
    if total == 0:
        mob_score = 1.0
    else:
        mob_ratio = mob / total
        # 모바일 비중 높을수록 실시간성 ↑ (0.6~1.4 범위)
        mob_score = 0.6 + mob_ratio * 0.8

    season   = seasonal_bonus(kw)
    pattern  = 1.3 if any(p in kw for p in REALTIME_PATTERNS) else 1.0

    raw = round(mob_score * season * pattern, 3)
    # 실시간성 플래그 (1.5 이상이면 급상승 마킹)
    return raw

def is_realtime_hot(rt_score, srch, doc):
    """실시간 급상승 마킹 기준"""
    return rt_score >= 1.3 and srch >= 500

def opportunity_score(doc, srch):
    """기회점수 = 검색량 / (문서량 + 1)"""
    return round(srch / (doc + 1), 4)

def final_score(opp, rt, intent_coef):
    """최종점수 = 기회점수 × 실시간점수 × 구매의도계수"""
    return round(opp * rt * intent_coef, 4)

def content_direction(kw):
    """키워드 패턴으로 콘텐츠 방향 자동 추천"""
    patterns = [
        (["맛집","식당","음식점","이자카야","오마카세"], "방문 후기 + 메뉴 추천형"),
        (["카페","커피","디저트","케이크","빵"],         "카페 탐방 후기형"),
        (["레시피","만들기","요리법","집밥","끓이기"],   "단계별 레시피 가이드형"),
        (["여행","코스","명소","가볼만한","당일치기"],    "여행 코스 추천형"),
        (["숙소","펜션","호텔","글램핑","풀빌라"],       "숙소 비교 추천형"),
        (["추천","비교","순위","TOP","리스트"],           "비교 추천 리스트형"),
        (["방법","하는법","하는방법","방식","설명"],      "방법 안내형 (How-to)"),
        (["증상","원인","이유","왜","어떻게"],            "정보 제공형 (FAQ)"),
        (["가격","비용","요금","얼마","견적"],            "비용 정보 안내형"),
        (["후기","리뷰","사용기","솔직한","체험"],        "실사용 후기형"),
        (["운동","헬스","다이어트","필라테스","요가"],    "운동 정보 + 루틴 안내형"),
        (["제품","구매","쇼핑","구입","살때"],            "제품 비교 구매 가이드형"),
        (["강아지","고양이","반려","펫"],                 "반려동물 정보 + 경험 공유형"),
        (["코디","룩","패션","스타일","옷"],              "코디 스타일링 가이드형"),
        (["공부","학습","시험","자격증","취업"],          "학습 정보 + 경험 공유형"),
        (["투자","주식","부동산","재테크","절약"],        "재테크 정보 + 경험 공유형"),
        (["게임","공략","챔피언","직업","캐릭터"],        "게임 공략 + 팁 정보형"),
        (["영화","드라마","넷플릭스","시리즈","왓챠"],   "콘텐츠 리뷰 + 추천형"),
        (["책","소설","독서","베스트셀러","에세이"],      "책 리뷰 + 추천형"),
    ]
    for keywords, direction in patterns:
        if any(p in kw for p in keywords):
            return direction
    return "정보 제공 + 경험 공유형"

def tier_classify(doc, srch, opp):
    """SEO 티어 분류: 최종추천 / 2차후보 / 1차후보"""
    if doc <= 10000 and srch >= 1000 and opp >= 0.1:
        return "최종추천"
    if doc <= 30000 and srch >= 500 and opp >= 0.02:
        return "2차후보"
    return "1차후보"

def judge(doc, srch):
    if doc < 0:
        return {"g": "분석불가", "e": "❓", "c": "#6b7280"}
    ld = doc <= GOLD_MAX_DOCS        # 발행량 10,000 이하
    hs = srch >= 500                 # 검색량 500 이상
    md = doc <= 30000                # 발행량 30,000 이하
    hi_ratio = srch > 0 and (srch / doc) >= 0.3  # 검색량이 발행량의 30% 이상
    if ld and hs:            return {"g": "황금키워드",     "e": "🏆", "c": "#F5A623"}
    if ld and srch <= 0:     return {"g": "검색량확인필요", "e": "🔍", "c": "#9B59B6"}
    if ld:                   return {"g": "블루오션",        "e": "🌊", "c": "#3498DB"}
    if md and hs and hi_ratio: return {"g": "추천",          "e": "✅", "c": "#27AE60"}
    if md and hs:            return {"g": "보통",             "e": "⚠️", "c": "#E67E22"}
    return                         {"g": "경쟁과다",          "e": "❌", "c": "#E74C3C"}

# ═══════════════════════════════════════════
# 자동 발굴 백그라운드
# ═══════════════════════════════════════════
def run_scan(target, topic_key, min_search, comp_ratio=0.5):
    if topic_key == "all":
        label = "🌐 전체"
        all_seeds = []
        seen = set()
        for info in TOPICS.values():
            for s in info.get("seeds", []):
                if s not in seen:
                    seen.add(s)
                    all_seeds.append(s)
        seeds = all_seeds
    else:
        info   = TOPICS.get(topic_key, {})
        label  = info.get("label", topic_key)
        seeds  = info.get("seeds", [])
    stop_event  = threading.Event()
    found_list  = []

    try:
        with scan_lock:
            scan_state.update({"running": True, "progress": 0, "checked": 0,
                                "found": 0, "results": [], "log": [], "phase":
                                f"[{label}] 파생 시드 생성 중..."})

        # ── Phase 0: 수식어 조합으로 파생 시드 대량 생성 ──
        derived = expand_seeds_with_modifiers(seeds, topic_key, max_extra=150)
        all_seeds = seeds + derived
        with scan_lock:
            scan_state["log"].append(
                f"원본 시드 {len(seeds)}개 + 파생 시드 {len(derived)}개 = 총 {len(all_seeds)}개")
            scan_state["phase"] = f"[{label}] 1차 연관 키워드 수집 중..."

        # ── Phase 1-A: 시드 배치 병렬 keywordstool ──
        batches_a = [all_seeds[i:i+5] for i in range(0, len(all_seeds), 5)]
        hop1_kw   = {}
        done_seeds = 0

        with ThreadPoolExecutor(max_workers=8) as ex:
            fmap = {ex.submit(get_related, b): b for b in batches_a}
            for f in as_completed(fmap):
                if not scan_state["running"]:
                    break
                hop1_kw.update(f.result())
                done_seeds += len(fmap[f])
                with scan_lock:
                    scan_state["log"].append(
                        f"1차 시드 {done_seeds}/{len(seeds)} 처리 → 1차 연관어 {len(hop1_kw)}개")

        # ── Phase 1-B: 2-hop 탐색 (1차 연관어 → 2차 연관어) ──
        # 검색량 500~30000 범위의 1차 연관어를 시드로 재사용 → 틈새 키워드 발굴
        with scan_lock:
            scan_state["phase"] = f"[{label}] 2차 연관 키워드 수집 중 (2-hop)..."

        hop2_seeds = [k for k, v in hop1_kw.items()
                      if 500 <= v["total"] <= 30000][:200]  # 상위 200개만
        import random
        random.shuffle(hop2_seeds)  # 다양성 확보를 위해 랜덤 순서

        hop2_kw = {}
        batches_b = [hop2_seeds[i:i+5] for i in range(0, len(hop2_seeds), 5)]
        done_hop2 = 0

        with ThreadPoolExecutor(max_workers=8) as ex:
            fmap2 = {ex.submit(get_related, b): b for b in batches_b}
            for f in as_completed(fmap2):
                if not scan_state["running"]:
                    break
                hop2_kw.update(f.result())
                done_hop2 += len(fmap2[f])
                if done_hop2 % 20 == 0:
                    with scan_lock:
                        scan_state["log"].append(
                            f"2차 탐색 {done_hop2}/{len(hop2_seeds)} → 2차 연관어 {len(hop2_kw)}개")

        # 1차 + 2차 합산 (2차가 우선: 더 틈새)
        all_kw = {**hop1_kw, **hop2_kw}
        with scan_lock:
            scan_state["log"].append(
                f"총 후보 {len(all_kw)}개 (1차:{len(hop1_kw)}, 2차:{len(hop2_kw)})")

        # ── 사전 필터 1: 최소 검색량 & 기존 제외 ──
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
                    f"관련성 필터: {before}개 → {len(candidates)}개")

        # 검색량/발행량 비율 예측이 높은 것 먼저 (절대 검색량 순 X)
        # 검색량이 적당하고 경쟁이 낮을 것 같은 키워드를 앞으로
        # 기준: 검색량 min_search~50000 범위 우선 (너무 높으면 이미 경쟁 심함)
        def priority_score(item):
            k, v = item
            srch = v["total"]
            # 검색량이 적당한 범위(1000~20000)에 높은 점수, 너무 많으면 감점
            if srch <= 20000:
                return srch
            else:
                return 20000 - (srch - 20000) * 0.5

        kw_items = sorted(candidates.items(), key=priority_score, reverse=True)

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

                if doc >= 0 and (doc == 0 or sr["total"] >= doc * comp_ratio):
                    j           = judge(doc, sr["total"])
                    opp         = opportunity_score(doc, sr["total"])
                    rt          = realtime_score(sr["pc"], sr["mob"], kw)
                    intent_coef = purchase_intent_coef(kw)
                    fscore      = final_score(opp, rt, intent_coef)
                    tier        = tier_classify(doc, sr["total"], opp)
                    hot         = is_realtime_hot(rt, sr["total"], doc)
                    entry = {
                        "keyword":     kw,
                        "topic":       topic_key,
                        "doc":         doc,
                        "srch":        sr["total"],
                        "pc":          sr["pc"],
                        "mob":         sr["mob"],
                        "mob_ratio":   round(sr["mob"] / sr["total"], 2) if sr["total"] else 0,
                        "comp":        round(doc / sr["total"], 2) if sr["total"] else None,
                        "opp_score":   opp,
                        "rt_score":    rt,
                        "intent_coef": intent_coef,
                        "final_score": fscore,
                        "realtime_hot":hot,
                        "tier":        tier,
                        "content_dir": content_direction(kw),
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
    result = {"all": "🌐 전체 (모든 카테고리)"}
    result.update({k: v["label"] for k, v in TOPICS.items()})
    return jsonify(result)

@app.route("/scan/start", methods=["POST"])
def scan_start():
    if scan_state["running"]:
        return jsonify({"error": "이미 발굴 중입니다"}), 400
    data       = request.json or {}
    topic      = data.get("topic", "")
    target     = max(1, int(data.get("target", 100)))
    min_search = max(100, min(20000, int(data.get("min_search", 1000))))
    comp_ratio = max(0.1, min(1.0, float(data.get("comp_ratio", 0.5))))
    if topic != "all" and topic not in TOPICS:
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

def _load_topic_results(topic):
    if topic == "all":
        seen = {}
        for tk in TOPICS:
            for r in load_scan(tk):
                kw = r["keyword"]
                cur_opp = r.get("opp_score", opportunity_score(r.get("doc",0), r.get("srch",0)))
                prv_opp = seen[kw].get("opp_score", 0) if kw in seen else 0
                if kw not in seen or cur_opp > prv_opp:
                    seen[kw] = r
        results = list(seen.values())
    else:
        results = load_scan(topic)
        words = TOPIC_FILTERS.get(topic, [])
        if words:
            results = [r for r in results if any(w in r["keyword"] for w in words)]
    # 구 데이터 보정 (새 필드 없으면 계산)
    for r in results:
        doc  = r.get("doc", 0)
        srch = r.get("srch", 0)
        pc   = r.get("pc", 0)
        mob  = r.get("mob", 0)
        kw   = r.get("keyword", "")
        if "opp_score" not in r:
            r["opp_score"] = opportunity_score(doc, srch)
        if "rt_score" not in r:
            r["rt_score"] = realtime_score(pc, mob, kw)
        if "intent_coef" not in r:
            r["intent_coef"] = purchase_intent_coef(kw)
        if "final_score" not in r:
            r["final_score"] = final_score(r["opp_score"], r["rt_score"], r["intent_coef"])
        if "realtime_hot" not in r:
            r["realtime_hot"] = is_realtime_hot(r["rt_score"], srch, doc)
        if "tier" not in r:
            r["tier"] = tier_classify(doc, srch, r["opp_score"])
        if "content_dir" not in r:
            r["content_dir"] = content_direction(kw)
        if "mob_ratio" not in r:
            r["mob_ratio"] = round(mob / srch, 2) if srch else 0
    results.sort(key=lambda x: x["final_score"], reverse=True)
    return results

@app.route("/scan/results")
def scan_results():
    topic = request.args.get("topic", "")
    return jsonify(_load_topic_results(topic))

@app.route("/scan/top20")
def scan_top20():
    topic   = request.args.get("topic", "")
    results = _load_topic_results(topic)
    final   = [r for r in results if r.get("tier") == "최종추천"][:20]
    if len(final) < 20:
        second = [r for r in results if r.get("tier") == "2차후보"][:20 - len(final)]
        final  = final + second
    return jsonify(final[:20])

@app.route("/scan/export")
def scan_export():
    import csv, io
    topic   = request.args.get("topic", "")
    results = _load_topic_results(topic)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["순위","키워드","월간검색수","PC검색","모바일검색","모바일비중",
                     "문서량","경쟁도(발행/검색)",
                     "기회점수","실시간점수","구매의도계수","최종점수",
                     "티어","등급","급상승여부","콘텐츠방향","수집일시"])
    for i, r in enumerate(results, 1):
        writer.writerow([
            i,
            r.get("keyword",""),
            r.get("srch",""),
            r.get("pc",""),
            r.get("mob",""),
            r.get("mob_ratio",""),
            r.get("doc",""),
            r.get("comp",""),
            r.get("opp_score",""),
            r.get("rt_score",""),
            r.get("intent_coef",""),
            r.get("final_score",""),
            r.get("tier",""),
            r.get("grade",""),
            "급상승" if r.get("realtime_hot") else "",
            r.get("content_dir",""),
            r.get("searched_at",""),
        ])
    from flask import Response
    filename = f"keywords_{topic}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    return Response(
        "\ufeff" + buf.getvalue(),  # BOM for Excel UTF-8
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
    )

@app.route("/scan/clear", methods=["POST"])
def scan_clear():
    topic = (request.json or {}).get("topic", "")
    if topic == "all":
        for tk in TOPICS:
            with open(scan_file(tk), "w", encoding="utf-8") as f:
                json.dump([], f)
    elif topic in TOPICS:
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
      <button class="btn-clear-scan" onclick="showTop20()" style="background:#F5A62322;border-color:#F5A62355;color:#F5A623">🏆 즉시작성 TOP20</button>
      <button class="btn-clear-scan" onclick="exportCSV()" style="background:#27AE6022;border-color:#27AE6055;color:#27AE60">⬇ CSV 저장</button>
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

  <!-- TOP20 섹션 -->
  <div id="top20Section" style="display:none;margin-bottom:18px">
    <div class="result-header" style="border-bottom:1px solid #F5A62344;margin-bottom:10px">
      <span class="result-title" style="color:#F5A623">🏆 즉시 작성 추천 키워드 TOP 20</span>
      <button onclick="document.getElementById('top20Section').style.display='none'"
              style="background:none;border:none;color:var(--mt);cursor:pointer;font-size:12px">✕ 닫기</button>
    </div>
    <div style="font-size:10px;color:var(--mt);margin-bottom:8px">
      기회점수(검색량÷발행량) 기준 상위 · 최종추천 우선 · 클릭하면 바로 분석
    </div>
    <div id="top20List"></div>
  </div>

  <div class="result-header">
    <span class="result-title">발굴된 키워드 (기회점수 순)</span>
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

const TIER_META = {
  '최종추천': {c:'#F5A623', bg:'#F5A62318', label:'🏆 최종추천'},
  '2차후보':  {c:'#27AE60', bg:'#27AE6018', label:'✅ 2차후보'},
  '1차후보':  {c:'#3498DB', bg:'#3498DB18', label:'🔵 1차후보'},
};

function renderScanItems(list, full) {
  const el = document.getElementById('scanResultList');
  if (!list.length) { el.innerHTML='<div class="empty-msg">발굴된 황금키워드가 없습니다</div>'; return; }
  const show = full ? list : list.slice(0,30);
  el.innerHTML = show.map((d,i) => {
    const ratio   = d.doc > 0 ? (d.srch/d.doc).toFixed(1) : '∞';
    const opp     = d.opp_score  != null ? d.opp_score.toFixed(2)  : '-';
    const rt      = d.rt_score   != null ? d.rt_score.toFixed(2)   : '-';
    const fs      = d.final_score!= null ? d.final_score.toFixed(2): '-';
    const mobPct  = d.mob_ratio  != null ? Math.round(d.mob_ratio*100)+'%' : '-';
    const tier    = d.tier || '1차후보';
    const tm      = TIER_META[tier] || TIER_META['1차후보'];
    const dir     = d.content_dir || '';
    const hotBadge = d.realtime_hot
      ? `<span style="font-size:10px;padding:2px 7px;border-radius:4px;background:#E74C3C18;color:#E74C3C;font-weight:700;border:1px solid #E74C3C44">🔥 급상승</span>`
      : '';
    return `<div class="result-item" onclick="goSearch('${esc(d.keyword)}')" style="border-color:${tm.c}33">
      <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
        <span style="font-size:10px;font-family:var(--m);color:var(--mt);min-width:20px">#${i+1}</span>
        <span class="ri-kw">${esc(d.keyword)}</span>
        <span style="font-size:10px;padding:2px 7px;border-radius:4px;background:${tm.bg};color:${tm.c};font-weight:700;border:1px solid ${tm.c}44">${tm.label}</span>
        ${hotBadge}
      </div>
      <div class="ri-stats" style="margin-top:4px">
        <span>발행 <b style="color:#dde1ec">${d.doc.toLocaleString()}</b></span>
        <span>검색 <b style="color:var(--gold)">${d.srch.toLocaleString()}</b></span>
        <span>모바일 <b style="color:#9B59B6">${mobPct}</b></span>
        <span>기회 <b style="color:#2ECC71">${opp}</b></span>
        <span>실시간 <b style="color:#E74C3C">${rt}</b></span>
        <span>최종 <b style="color:#F5A623">${fs}</b></span>
      </div>
      ${dir ? `<div style="font-size:10px;color:var(--mt);margin-top:3px">📝 ${esc(dir)}</div>` : ''}
    </div>`;
  }).join('');
  if (full) document.getElementById('scanResultCount').textContent = list.length+'개';
}

async function showTop20() {
  if (!selTopic){alert('주제를 먼저 선택하세요');return;}
  const res  = await fetch('/scan/top20?topic='+selTopic);
  const list = await res.json();
  const el   = document.getElementById('top20List');
  const sec  = document.getElementById('top20Section');
  sec.style.display = 'block';
  if (!list.length){el.innerHTML='<div class="empty-msg">추천 키워드가 없습니다. 먼저 발굴을 실행하세요.</div>';return;}
  el.innerHTML = list.map((d,i)=>{
    const tm    = TIER_META[d.tier||'1차후보'];
    const opp   = d.opp_score  !=null?d.opp_score.toFixed(2):'-';
    const rt    = d.rt_score   !=null?d.rt_score.toFixed(2):'-';
    const fs    = d.final_score!=null?d.final_score.toFixed(2):'-';
    const ratio = d.doc>0?(d.srch/d.doc).toFixed(1):'∞';
    const mobPct= d.mob_ratio!=null?Math.round(d.mob_ratio*100)+'%':'-';
    const hotBadge = d.realtime_hot
      ? `<span style="font-size:10px;padding:2px 6px;border-radius:4px;background:#E74C3C18;color:#E74C3C;font-weight:700">🔥 급상승</span>`:'';
    return `<div class="result-item" onclick="goSearch('${esc(d.keyword)}')" style="border-color:${tm.c}55">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <span style="font-size:13px;font-weight:900;color:${i<3?'#F5A623':'var(--mt)'};min-width:28px">${i+1}위</span>
        <span class="ri-kw">${esc(d.keyword)}</span>
        ${hotBadge}
      </div>
      <div class="ri-stats" style="margin-top:4px">
        <span>검색 <b style="color:var(--gold)">${d.srch.toLocaleString()}</b></span>
        <span>발행 <b style="color:#dde1ec">${d.doc.toLocaleString()}</b></span>
        <span>모바일 <b style="color:#9B59B6">${mobPct}</b></span>
        <span>기회 <b style="color:#2ECC71">${opp}</b></span>
        <span>실시간 <b style="color:#E74C3C">${rt}</b></span>
        <span>최종 <b style="color:#F5A623;font-size:12px">${fs}</b></span>
      </div>
      ${d.content_dir?`<div style="font-size:10px;color:#F5A623;margin-top:3px">📝 ${esc(d.content_dir)}</div>`:''}
    </div>`;
  }).join('');
}

function exportCSV() {
  if (!selTopic){alert('주제를 먼저 선택하세요');return;}
  window.open('/scan/export?topic='+selTopic,'_blank');
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
