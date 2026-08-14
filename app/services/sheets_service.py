class SheetsService:
    def __init__(self):
        pass
    
    def save_analysis(self, transcript: str, analysis: dict, user_id: str = "anonymous"):
        print(f"Saving analysis for {user_id}: {analysis.get('communication_tax_score')}")
        return True
