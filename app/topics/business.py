from .schema import Opportunity, Topic

INDUSTRIES = {
    'housing': ['부동산 중개·주거 서비스', '프롭테크'],
    'finance': ['금융교육', '핀테크', '재무관리 서비스', '경제·금융 교육 플랫폼'],
    'economy': ['일반 기업의 직원 교육 및 브랜드 콘텐츠', '경제·금융 교육 플랫폼'],
}


def assess(topic: Topic) -> Opportunity:
    score = topic.score.parts.business / 5 * 100 if topic.score else 60
    return Opportunity(b2b_fit_score=score, target_industries=INDUSTRIES[topic.category],
                       client_use_cases=['고객 온보딩용 생활경제 교육', '직원 복지·금융 문해력 교육'] if topic.category != 'economy' else ['뉴스를 생활비와 연결하는 직원 교육'],
                       sample_deliverables=['8장 하이브리드 인스타툰', '원자료·기준일이 담긴 검증 기록', '독자용 체크리스트'],
                       recommended_package='교육 캐러셀 + 체크리스트 + 선택형 쇼츠 파생',
                       compliance_risks=['특정 기업 광고로 전환 시 실제 서비스·자격·광고 표시·주장 근거 확인',
                                         '수익 보장·개인 맞춤 투자 권유 제외', '캐릭터·이미지 사용 권한 확인',
                                         *topic.compliance_flags])
