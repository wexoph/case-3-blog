import os, sqlite3
from pathlib import Path
from functools import wraps
from flask import Flask, g, request, redirect, url_for, flash, session, render_template
from werkzeug.security import generate_password_hash, check_password_hash
app=Flask(__name__); app.secret_key=os.environ.get('SECRET_KEY','local-study-secret-change-me'); DB=Path(__file__).parent/'instance'/'blog.sqlite3'; DB.parent.mkdir(exist_ok=True)
SCHEMA='''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL,bio TEXT DEFAULT ''); CREATE TABLE IF NOT EXISTS posts(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),title TEXT NOT NULL,body TEXT NOT NULL,tags TEXT DEFAULT '',visibility TEXT NOT NULL DEFAULT 'public',created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP); CREATE TABLE IF NOT EXISTS follows(follower_id INTEGER REFERENCES users(id),followed_id INTEGER REFERENCES users(id),PRIMARY KEY(follower_id,followed_id)); CREATE TABLE IF NOT EXISTS requests(requester_id INTEGER REFERENCES users(id),post_id INTEGER REFERENCES posts(id),created_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(requester_id,post_id)); CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY,post_id INTEGER REFERENCES posts(id),user_id INTEGER REFERENCES users(id),body TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);'''
def db():
 if 'db' not in g: g.db=sqlite3.connect(DB); g.db.row_factory=sqlite3.Row
 return g.db
@app.teardown_appcontext
def close(_):
 c=g.pop('db',None)
 if c:c.close()
with app.app_context(): db().executescript(SCHEMA); db().commit()
@app.context_processor
def inject():
 u=db().execute('select * from users where id=?',(session.get('uid'),)).fetchone() if session.get('uid') else None
 return {'current_user':u,'appname':'Блог-сообщество'}
def page(title,body):return render_template('base.html',title=title,body=body)
def login_required(fn):
 @wraps(fn)
 def w(*a,**kw):
  if not session.get('uid'): flash('Сначала войдите в аккаунт.'); return redirect(url_for('login'))
  return fn(*a,**kw)
 return w
@app.route('/')
def index():
 u=session.get('uid'); mode=request.args.get('mode','public'); term=request.args.get('q','').strip(); tag=request.args.get('tag','').strip(); sort=request.args.get('sort','new')
 sql="SELECT p.*,u.username FROM posts p JOIN users u ON u.id=p.user_id WHERE (p.visibility='public' OR p.user_id=?)"; params=[u or -1]
 if mode=='feed' and u: sql="SELECT p.*,u.username FROM posts p JOIN users u ON u.id=p.user_id JOIN follows f ON f.followed_id=u.id WHERE f.follower_id=? AND (p.visibility='public' OR p.user_id=?)"; params=[u,u]
 if term: sql+=' AND (p.title LIKE ? OR p.body LIKE ?)'; params += [f'%{term}%',f'%{term}%']
 if tag: sql+=' AND (\',\'||p.tags||\',\' LIKE ?)'; params += [f'%,{tag},%']
 sql += ' ORDER BY p.created_at '+('ASC' if sort=='old' else 'DESC')
 posts=db().execute(sql,params).fetchall(); cards=''
 for p in posts:
  tags=' '.join('#'+t.strip() for t in p['tags'].split(',') if t.strip()); cards+=f"<article class=card><small>@{p['username']} · {p['created_at']}</small><h2><a href='{url_for('post',post_id=p['id'])}'>{p['title']}</a></h2><p>{p['body'][:260]}</p><div class=tags>{tags}</div><small>{'Запросный доступ' if p['visibility']=='request' else 'Публично'}</small></article>"
 tools="<div class=card><a class=button href='?mode=public'>Все публикации</a> <a class='button secondary' href='?mode=feed'>Лента подписок</a><form><label>Поиск<input name=q placeholder='слово из заголовка/текста' value='"+term+"'></label><label>Тег<input name=tag placeholder='например: java' value='"+tag+"'></label><label>Сортировка<select name=sort><option value=new>Сначала новые</option><option value=old "+('selected' if sort=='old' else '')+">Сначала старые</option></select></label><button>Применить</button></form>"+("<p><a class=button href='/new'>Написать публикацию</a></p>" if u else '')+"</div>"
 return page('Публикации',tools+(cards or '<div class=card>Публикаций пока нет. Зарегистрируйте ещё пользователя или создайте первую запись.</div>'))
@app.route('/register',methods=['GET','POST'])
def register():
 if request.method=='POST':
  name=request.form.get('username','').strip(); pwd=request.form.get('password','')
  if len(name)<3 or len(pwd)<8: flash('Имя — от 3 символов, пароль — от 8.'); return redirect(url_for('register'))
  try: db().execute('insert into users(username,password) values(?,?)',(name,generate_password_hash(pwd)));db().commit();flash('Аккаунт создан, войдите.');return redirect(url_for('login'))
  except sqlite3.IntegrityError:flash('Такое имя уже занято.')
 return page('Регистрация',"<div class=card><form method=post><label>Имя пользователя<input name=username required minlength=3></label><label>Пароль<input type=password name=password required minlength=8></label><button>Создать аккаунт</button></form></div>")
@app.route('/login',methods=['GET','POST'])
def login():
 if request.method=='POST':
  x=db().execute('select * from users where username=?',(request.form.get('username','').strip(),)).fetchone()
  if x and check_password_hash(x['password'],request.form.get('password','')):session['uid']=x['id'];return redirect(url_for('index'))
  flash('Неверное имя или пароль.')
 return page('Вход',"<div class=card><form method=post><label>Имя<input name=username required></label><label>Пароль<input type=password name=password required></label><button>Войти</button></form></div>")
@app.route('/logout')
def logout():session.clear();return redirect(url_for('index'))
@app.route('/new',methods=['GET','POST'])
@login_required
def new_post():
 if request.method=='POST':
  title=request.form.get('title','').strip(); body=request.form.get('body','').strip(); vis=request.form.get('visibility','public')
  if title and body and vis in ('public','request'):db().execute('insert into posts(user_id,title,body,tags,visibility) values(?,?,?,?,?)',(session['uid'],title,body,request.form.get('tags','').strip(),vis));db().commit();return redirect(url_for('index'))
  flash('Заполните заголовок и текст.')
 return page('Новая публикация',"<div class=card><form method=post><label>Заголовок<input name=title required></label><label>Текст<textarea name=body required></textarea></label><label>Теги, через запятую<input name=tags placeholder='java, учеба'></label><label>Доступ<select name=visibility><option value=public>Публичная</option><option value=request>Только по запросу автора</option></select></label><button>Опубликовать</button></form></div>")
@app.route('/post/<int:post_id>',methods=['GET','POST'])
def post(post_id):
 p=db().execute('select p.*,u.username from posts p join users u on u.id=p.user_id where p.id=?',(post_id,)).fetchone()
 if not p:return 'Не найдено',404
 uid=session.get('uid'); allowed=p['visibility']=='public' or uid==p['user_id'] or (uid and db().execute('select 1 from requests where requester_id=? and post_id=?',(uid,post_id)).fetchone())
 if not allowed:
  if request.method=='POST' and uid:db().execute('insert or ignore into requests(requester_id,post_id) values(?,?)',(uid,post_id));db().commit();flash('Запрос отправлен автору.')
  elif request.method=='POST':flash('Войдите, чтобы отправить запрос.')
  return page('Закрытая публикация',f"<div class=card><p>@{p['username']} ограничил доступ к этой записи.</p><form method=post><button>Запросить доступ</button></form></div>")
 comments=db().execute('select c.*,u.username from comments c join users u on u.id=c.user_id where post_id=? order by c.created_at',(post_id,)).fetchall();html=f"<div class=card><small>@{p['username']} · {p['created_at']}</small><h2>{p['title']}</h2><p>{p['body']}</p><p class=tags>{p['tags']}</p>"
 if uid==p['user_id']:html+=f"<a class=button href='{url_for('edit_post',post_id=post_id)}'>Редактировать</a> <form class=inline method=post action='{url_for('delete_post',post_id=post_id)}'><button>Удалить</button></form>"
 html+='</div><h2>Комментарии</h2>'
 if uid:html+=f"<div class=card><form method=post action='{url_for('comment',post_id=post_id)}'><textarea name=body required placeholder='Ваш комментарий'></textarea><button>Добавить</button></form></div>"
 html+=''.join(f"<div class=card><b>@{c['username']}</b><p>{c['body']}</p></div>" for c in comments)
 return page(p['title'],html)
@app.route('/post/<int:post_id>/comment',methods=['POST'])
@login_required
def comment(post_id):
 body=request.form.get('body','').strip(); p=db().execute('select * from posts where id=?',(post_id,)).fetchone()
 if p and body and (p['visibility']=='public' or p['user_id']==session['uid']):db().execute('insert into comments(post_id,user_id,body) values(?,?,?)',(post_id,session['uid'],body));db().commit()
 return redirect(url_for('post',post_id=post_id))
@app.route('/post/<int:post_id>/edit',methods=['GET','POST'])
@login_required
def edit_post(post_id):
 p=db().execute('select * from posts where id=? and user_id=?',(post_id,session['uid'])).fetchone()
 if not p:return 'Не найдено',404
 if request.method=='POST':db().execute('update posts set title=?,body=?,tags=?,visibility=?,updated_at=CURRENT_TIMESTAMP where id=?',(request.form['title'].strip(),request.form['body'].strip(),request.form.get('tags',''),request.form['visibility'],post_id));db().commit();return redirect(url_for('post',post_id=post_id))
 return page('Редактировать',f"<div class=card><form method=post><label>Заголовок<input name=title required value='{p['title']}'></label><label>Текст<textarea name=body required>{p['body']}</textarea></label><label>Теги<input name=tags value='{p['tags']}'></label><label>Доступ<select name=visibility><option value=public>Публичная</option><option value=request {'selected' if p['visibility']=='request' else ''}>По запросу</option></select></label><button>Сохранить</button></form></div>")
@app.route('/post/<int:post_id>/delete',methods=['POST'])
@login_required
def delete_post(post_id):db().execute('delete from comments where post_id=?',(post_id,));db().execute('delete from requests where post_id=?',(post_id,));db().execute('delete from posts where id=? and user_id=?',(post_id,session['uid']));db().commit();return redirect(url_for('index'))
@app.route('/user/<username>',methods=['GET','POST'])
def profile(username):
 u=db().execute('select * from users where username=?',(username,)).fetchone()
 if not u:return 'Пользователь не найден',404
 me=session.get('uid');
 if request.method=='POST' and me and me!=u['id']:
  if request.form.get('action')=='follow':db().execute('insert or ignore into follows values(?,?)',(me,u['id']))
  else:db().execute('delete from follows where follower_id=? and followed_id=?',(me,u['id']))
  db().commit()
 mine=(me==u['id']);posts=db().execute('select * from posts where user_id=? and (visibility="public" or ?=1) order by created_at desc',(u['id'],int(mine))).fetchall(); html=f"<div class=card><h2>@{u['username']}</h2><p>{u['bio'] or 'Профиль автора'}</p>"
 if me and not mine:
  following=db().execute('select 1 from follows where follower_id=? and followed_id=?',(me,u['id'])).fetchone(); html+=f"<form method=post><button name=action value={'unfollow' if following else 'follow'}>{'Отписаться' if following else 'Подписаться'}</button></form>"
 html+='</div>'
 for p in posts:html+=f"<article class=card><a href='{url_for('post',post_id=p['id'])}'><h3>{p['title']}</h3></a><p>{p['body'][:180]}</p><small>{p['visibility']}</small></article>"
 if mine:
  reqs=db().execute('select r.*,u.username,p.title,p.id pid from requests r join users u on u.id=r.requester_id join posts p on p.id=r.post_id where p.user_id=? order by r.created_at desc',(me,)).fetchall(); html+='<h2>Запросы доступа</h2>'
  html+=''.join(f"<div class=card>@{r['username']} запросил «{r['title']}» · <a href='{url_for('post',post_id=r['pid'])}'>Открыть запись</a></div>" for r in reqs) or '<div class=card>Запросов пока нет.</div>'
 return page('Профиль',html)
if __name__=='__main__':app.run(debug=True)
