from fastapi import FastAPI, Request, Form, Depends, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from dotenv import load_dotenv

import cloudinary
import cloudinary.uploader
import models

from database import Base, engine, get_db
from security import hash_password, verify_password
from auth import create_access_token, verify_access_token, get_current_user
from fastapi.staticfiles import StaticFiles
import os
import uuid


# =============================
# Configuration
# =============================

load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

templates = Jinja2Templates(directory="templates")


# =============================
# Cloudinary
# =============================

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)


# =============================
# Cleanup expired videos
# =============================

def cleanup_expired_videos():

    db = next(get_db())

    try:

        expired_videos = db.query(models.Video).filter(
            models.Video.expires_at <= datetime.utcnow()
        ).all()

        for video in expired_videos:

            if video.cloudinary_public_id:

                try:

                    cloudinary.uploader.destroy(
                        video.cloudinary_public_id,
                        resource_type="video",
                        invalidate=True
                    )

                except Exception as e:

                    print(
                        "Cloudinary deletion failed:",
                        e
                    )

            db.delete(video)

        db.commit()

    except Exception as e:

        db.rollback()

        print(
            "Cleanup error:",
            e
        )

    finally:

        db.close()


scheduler = BackgroundScheduler()

scheduler.add_job(
    cleanup_expired_videos,
    "interval",
    minutes=10
)

scheduler.start()


# =============================
# Home
# =============================

@app.get("/")
def home(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )


# =============================
# Signup
# =============================

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


# =============================
# Login
# =============================

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

    if not verify_password(
        password,
        user.password
    ):

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


# =============================
# Upload video
# =============================

@app.post("/upload")
def upload_video(
    request: Request,
    video: UploadFile = File(...),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):

    stored_filename = f"{uuid.uuid4()}.mp4"

    video_result = cloudinary.uploader.upload(
        video.file,
        resource_type="video",
        folder="storydrop/videos"
    )

    video_url = video_result["secure_url"]

    video_public_id = video_result["public_id"]

    thumbnail_url = cloudinary.CloudinaryVideo(
        video_public_id
    ).build_url(
        format="jpg",
        transformation=[
            {
                "start_offset": "1"
            }
        ],
        secure=True
    )

    new_video = models.Video(
        original_filename=video.filename,
        stored_filename=stored_filename,
        thumbnail=None,
        cloudinary_video_url=video_url,
        cloudinary_thumbnail_url=thumbnail_url,
        cloudinary_public_id=video_public_id,
        owner_id=current_user.id,
        expires_at=datetime.utcnow() + timedelta(hours=24),
        views=0
    )

    db.add(new_video)

    db.commit()

    db.refresh(new_video)

    return {
        "message": "Video uploaded successfully",
        "original_filename": video.filename,
        "stored_filename": stored_filename,
        "thumbnail": None,
        "cloudinary_video": video_url,
        "cloudinary_thumbnail": thumbnail_url
    }


# =============================
# Delete video
# =============================

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

    if video.cloudinary_public_id:

        try:

            cloudinary.uploader.destroy(
                video.cloudinary_public_id,
                resource_type="video",
                invalidate=True
            )

        except Exception as e:

            print(
                "Cloudinary deletion failed:",
                e
            )

    db.delete(video)

    db.commit()

    return {
        "message": "Video deleted successfully"
    }


# =============================
# My videos
# =============================

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


# =============================
# Watch video
# =============================

@app.get(
    "/watch/{video_id}",
    response_class=HTMLResponse
)
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

        return HTMLResponse(
            "Video not found",
            status_code=404
        )

    return templates.TemplateResponse(
        request=request,
        name="watch_video.html",
        context={
            "request": request,
            "video": video,
            "current_time": datetime.utcnow()
        }
    )


# =============================
# Public share link
# =============================

@app.get("/v/{stored_filename}")
def view_video(
    stored_filename: str,
    db: Session = Depends(get_db)
):

    video = db.query(models.Video).filter(
        models.Video.stored_filename == stored_filename
    ).first()

    if not video:

        return {
            "message": "Video not found"
        }

    if (
        video.expires_at
        and video.expires_at <= datetime.utcnow()
    ):

        return {
            "message": "This video has expired"
        }

    video.views += 1

    db.commit()

    return RedirectResponse(
        url=video.cloudinary_video_url,
        status_code=302
    )


# =============================
# Upload page
# =============================

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


# =============================
# Dashboard
# =============================

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
            "videos": videos,
            "current_time": datetime.utcnow()
        }
    )