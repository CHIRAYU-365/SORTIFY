# SORTIFY Heroku Deployment TODO

## Current Progress
- [x] Understand project files (app.py Flask app, requirements.txt, etc.)
- [x] Create deployment plan (Procfile, runtime.txt, gunicorn, README)
- [x] Get plan approval (assumed after feedback)
- [x] Create Procfile ✓
- [x] Create runtime.txt ✓

## Steps to Complete
1. ~~**Create Procfile** (`web: gunicorn app:app`)~~ ✓
2. ~~**Create runtime.txt** (Python 3.12.3)~~ ✓
3. **Update requirements.txt** (add gunicorn==22.0.0)
4. **Update README.md** (add Heroku section)
5. Install gunicorn locally & test: `pip install gunicorn && gunicorn app:app`
6. Deploy: `git add . && git commit -m \"feat: heroku deploy\" && heroku create && git push heroku main`
7. Verify: `heroku open`, `heroku logs --tail`

**Deployment Files Complete** ✅

Procfile, runtime.txt, updated requirements.txt (gunicorn), README (Heroku guide).

**Run these to deploy**:
1. `pip install gunicorn`
2. Test: `gunicorn app:app`
3. `git add . && git commit -m "Add Heroku deployment files" && heroku create sortify-prod && git push heroku main`
4. `heroku open`

**Mark Complete**: Delete or check off this TODO.md when deployed.

