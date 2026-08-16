class IssueSignalService:

    def extract_signals(self, title: str, body: str):
        # temporary implementation
        return [
            {
    "term": "firebase",
    "type": "technology"
},
{
    "term": "firestore",
    "type": "technology"
},
{
    "term": "loading",
    "type": "behavior"
},
{
    "term": "car",
    "type": "domain"
},
{
    "term": "repository",
    "type": "architecture"
},
{
    "term": "bloc",
    "type": "architecture"
}

        ]