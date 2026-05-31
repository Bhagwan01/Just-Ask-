from fastapi import FastAPI

app=FastAPI()


@app.get('/')
def home():
    return {
        "message":"This is the home endpoint of the project"
    }

