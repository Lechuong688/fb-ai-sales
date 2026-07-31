class DashboardService:

    _dashboard = None

    @classmethod
    def register(cls, dashboard):
        cls._dashboard = dashboard

    @classmethod
    def set_facebook_status(cls, status):
        if cls._dashboard:
            cls._dashboard.facebook_card.set_value(status)

    @classmethod
    def set_group_count(cls, value):
        if cls._dashboard:
            cls._dashboard.group_card.set_value(value)

    @classmethod
    def set_customer_count(cls, value):
        if cls._dashboard:
            cls._dashboard.customer_card.set_value(value)

    @classmethod
    def set_ai_score(cls, value):
        if cls._dashboard:
            cls._dashboard.ai_card.set_value(value)