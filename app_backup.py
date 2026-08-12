import subprocess
from fastapi import FastAPI, Request, Form, Depends
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from security import hash_password
from security import verify_password
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import models
from database import Base, engine,get_db
from fastapi.responses import RedirectResponse
from fastapi import UploadFile, File
import shutil
import os
import uuid
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

from auth import (
    create_access_token,
    verify_access_token,
    get_current_user
)

Base.metadata.create_all(bind=engine)

app = FastAPI()

templates = Jinja2Templates(directory="templates")

load_dotenv()

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

def cleanup_expired_videos():
    db = next(get_db())

    try:
        expired_videos = db.query(models.Video).filter(
            models.Video.expires_at <= datetime.utcnow()
        ).all()

        for video in expired_videos:

            # Delete video file
            video_path = os.path.join(
                "uploads",
                video.stored_filename
            )

            if os.path.exists(video_path):
                os.remove(video_path)

            # Delete thumbnail
            if video.thumbnail:
                thumbnail_path = os.path.join(
                    "thumbnails",
                    video.thumbnail
                )

                if os.path.exists(thumbnail_path):
                    os.remove(thumbnail_path)

            # Delete database record
            db.delete(video)

        db.commit()

    finally:
        db.close()
scheduler = BackgroundScheduler()

scheduler.add_job(
    cleanup_expired_videos,
    "interval",
    minutes=10
)

scheduler.start()

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )

@app.get("/signup")
def signup(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="signup.html"
    )

@app.post("/signup")
def create_account(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    existing_user = db.query(models.User).filter(
        models.User.email == email
    ).first()

    if existing_user:
        return {
            "message": "Email already registered"
        }

    user = models.User(
        email=email,
        password=hash_password(password)
    )

    db.add(user)
    db.commit()

    return {
        "message": "Account created successfully"
    }

@app.get("/login")
def login(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html"
    )

@app.post("/login")
def login_user(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(
        models.User.email == email
    ).first()

    if user is None:
        return {
            "message": "Email not found"
        }

    if not verify_password(password, user.password):
        return {
            "message": "Wrong password"
        }

    token = create_access_token(
        {
            "sub": user.email
        }
    )

    response = RedirectResponse(
        url="/dashboard",
        status_code=303
    )

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True
    )

    return response


@app.get("/test")
def test():
    payload = verify_access_token(
"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzYW5rYXJsYWNodTY4MTBAZ21haWwuY29tIiwiZXhwIjoxNzgzNDM0MTQ3fQ.fRb-Xw8mHDHWabaWsyWQDJlIiU522y-QTw8n9UknP5Q"    )
    
    return payload

@app.post("/upload")
def upload_video(
    video: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("thumbnails", exist_ok=True)

    extension = os.path.splitext(video.filename)[1]
    unique_filename = f"{uuid.uuid4()}{extension}"

    file_path = os.path.join(
        "uploads",
        unique_filename
    )

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(video.file, buffer)

    thumbnail_name = f"{uuid.uuid4()}.jpg"

    thumbnail_path = os.path.join(
        "thumbnails",
        thumbnail_name
    )

    subprocess.run([
        "ffmpeg",
        "-i",
        file_path,
        "-ss",
        "00:00:01",
        "-frames:v",
        "1",
        thumbnail_path
    ])

    video_data = models.Video(
        original_filename=video.filename,
        stored_filename=unique_filename,
        thumbnail=thumbnail_name,
        owner_id=current_user.id,
        expires_at=datetime.utcnow() + timedelta(hours=24)
    )

    db.add(video_data)
    db.commit()

    return {
        "message": "Video uploaded successfully",
        "original_filename": video.filename,
        "stored_filename": unique_filename,
        "thumbnail": thumbnail_name
    }

@app.delete("/delete/{video_id}")
def delete_video(
    video_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    video = db.query(models.Video).filter(
        models.Video.id == video_id,
        models.Video.owner_id == current_user.id
    ).first()

    if video is None:
        return {
            "message": "Video not found"
        }

    # Delete video file
    video_path = os.path.join(
        "uploads",
        video.stored_filename
    )

    if os.path.exists(video_path):
        os.remove(video_path)

    # Delete thumbnail if it exists
    if video.thumbnail:
        thumbnail_path = os.path.join(
            "thumbnails",
            video.thumbnail
        )

        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)

    # Delete database record
    db.delete(video)
    db.commit()

    return {
        "message": "Video deleted successfully"
    }

@app.get("/my-videos")
def my_videos(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    videos = db.query(models.Video).filter(
        models.Video.owner_id == current_user.id
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="my_videos.html",
        context={
            "videos": videos,
            "user": current_user,
            "request": request
        }
    )
    
from fastapi.responses import HTMLResponse, FileResponse

@app.get("/watch/{video_id}", response_class=HTMLResponse)
def watch_video(
    request: Request,
    video_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    video = db.query(models.Video).filter(
        models.Video.id == video_id,
        models.Video.owner_id == current_user.id
    ).first()

    if video is None:
        return HTMLResponse("Video not found", status_code=404)

    return templates.TemplateResponse(
        request=request,
        name="watch_video.html",
        context={
             "request": request,
             "video": video
}
    )

@app.get("/stream/{video_id}")
def stream_video(
    video_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    video = db.query(models.Video).filter(
        models.Video.id == video_id,
        models.Video.owner_id == current_user.id
    ).first()

    if video is None:
        return {"message": "Video not found"}

    return FileResponse(
        path=f"uploads/{video.stored_filename}",
        media_type="video/mp4"
    )


@app.get("/v/{stored_filename}")
def public_video(
    request: Request,
    stored_filename: str,
    db: Session = Depends(get_db)
):
    video = db.query(models.Video).filter(
        models.Video.stored_filename == stored_filename
    ).first()

    if video is None:
        return {"message": "Video not found"}

    if datetime.utcnow() > video.expires_at:

        file_path = os.path.join(
            "uploads",
            video.stored_filename
        )

        if os.path.exists(file_path):
            os.remove(file_path)

        db.delete(video)
        db.commit()

        return templates.TemplateResponse(
            request=request,
            name="expired.html"
        )
    video.views += 1
    db.commit()

    return templates.TemplateResponse(
        request=request,
        name="public_video.html",
        context={
            "request": request,
            "video": video
        }
    )
@app.get("/public-stream/{stored_filename}")
def public_stream(
    stored_filename: str,
    db: Session = Depends(get_db)
):
    video = db.query(models.Video).filter(
        models.Video.stored_filename == stored_filename
    ).first()

    if video is None:
        return {"message": "Video not found"}

    # Check expiration
    if datetime.utcnow() > video.expires_at:

        file_path = os.path.join(
            "uploads",
            video.stored_filename
        )

        if os.path.exists(file_path):
            os.remove(file_path)

        if video.thumbnail:
            thumbnail_path = os.path.join(
                "thumbnails",
                video.thumbnail
            )

            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)

        db.delete(video)
        db.commit()

        return {"message": "Video has expired"}

    file_path = os.path.join(
        "uploads",
        video.stored_filename
    )

    if not os.path.exists(file_path):
        return {"message": "Video file not found"}

    return FileResponse(
        file_path,
        media_type="video/mp4"
    )
@app.get("/upload")
def upload(
    request: Request,
    current_user=Depends(get_current_user)
):
   return templates.TemplateResponse(
    request=request,
    name="upload.html",
    context={
        "request": request,
        "user": current_user
    }
)

@app.get("/dashboard")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    videos = db.query(models.Video).filter(
        models.Video.owner_id == current_user.id
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            "user": current_user,
            "videos": videos
        }
    )

@app.get("/thumbnail/{filename}")
def get_thumbnail(filename: str):
    return FileResponse(
        f"thumbnails/{filename}",
        media_type="image/jpeg"
    ) 