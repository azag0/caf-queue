from flask import Flask, request, url_for, render_template, session, abort, redirect
from flask_sqlalchemy import SQLAlchemy
import http.client
import urllib
from datetime import datetime
from collections import defaultdict
from functools import wraps


app = Flask(__name__)
app.config.from_envvar('CONF')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///{}/queue.db'.format(app.root_path)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

date_format = '%Y-%m-%d %H:%M:%S'


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True)
    token = db.Column(db.String(10), unique=True)
    password = db.Column(db.String(40))
    pushover = db.Column(db.String(20))
    queues = db.relationship('Queue', backref='user', lazy='dynamic')

    def __init__(self, name, password, token, pushover=None):
        self.name = name
        self.password = password
        self.token = token
        self.pushover = pushover


class Queue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    date_created_str = db.Column(db.String(30))
    done = db.Column(db.Boolean)
    tasks = db.relationship('Task', backref='queue', lazy='dynamic')

    def __init__(self, user_id):
        self.user_id = user_id
        self.date_created_str = datetime.now().strftime(date_format)
        self.done = False

    @property
    def date_created(self):
        return datetime.strptime(self.date_created_str, date_format)

    @property
    def date_changed(self):
        dates = [task.date_changed for task in self.tasks]
        return max(dates) if dates else self.date_created

    @property
    def task_states(self):
        states = defaultdict(int)
        for task in self.tasks:
            states[task.state] += 1
        return dict(states)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(50))
    state = db.Column(db.String(20))
    caller = db.Column(db.String(100))
    date_changed_str = db.Column(db.String(20))
    label = db.Column(db.String(200))
    queue_id = db.Column(db.Integer, db.ForeignKey('queue.id'))

    def __init__(self, queue_id, token, label='', state='Waiting', changed=None):
        self.queue_id = queue_id
        self.token = token
        self.label = label
        self.state = state
        self.caller = None
        self.date_changed_str = changed or datetime.now().strftime(date_format)

    def __repr__(self):
        return 'Task({})'.format(', '.join(map(repr, [
            self.queue_id, self.token, self.label, self.state, self.date_changed_str
        ])))

    @property
    def date_changed(self):
        return datetime.strptime(self.date_changed_str, date_format)

    def change_state(self, state, caller=None):
        self.state = state
        self.date_changed_str = datetime.now().strftime(date_format)
        if caller:
            self.caller = caller


class Pushover(db.Model):
    token = db.Column(db.String(20), primary_key=True)

    def __init__(self, token):
        self.token = token


def pushover(user, msg):
    token = Pushover.query.first().token
    if not token:
        return
    conn = http.client.HTTPSConnection('api.pushover.net:443')
    conn.request('POST',
                 '/1/messages.json',
                 urllib.parse.urlencode({
                     'token': token,
                     'user': user,
                     'message': msg}),
                 {'Content-type': 'application/x-www-form-urlencoded'})
    conn.getresponse()


@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('user', username=session['username']))
    else:
        return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        user = User.query.filter_by(
            name=username,
            password=request.form['password']
        ).first()
        if not user:
            return redirect(url_for('login'))
        session['username'] = username
        return redirect(url_for('user', username=session['username']))
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))


def authenticated(view):
    @wraps(view)
    def authview(**kwargs):
        try:
            usertoken = kwargs.pop('usertoken')
        except KeyError:
            pass
        else:
            return view(user=User.query.filter_by(token=usertoken).first_or_404(), **kwargs)
        if 'username' not in session:
            return redirect(url_for('index'))
        username = kwargs.pop('username')
        if username != session['username']:
            abort(404)
        return view(User.query.filter_by(name=username).first_or_404(), **kwargs)
    return authview


@app.route('/user/<username>')
@authenticated
def user(user):
    rows = [(queue.id,
             str(queue.task_states),
             queue.date_created.strftime(date_format),
             queue.date_changed.strftime(date_format),
             )
            for queue in user.queues]
    return render_template(
        'user.html',
        usertoken=user.token,
        username=user.name,
        queues=reversed(rows)
    )


@app.route('/token/<usertoken>/submit', methods=['POST'])
@authenticated
def submit(user):
    tasklines = request.get_data().decode().strip().split('\n')
    if not tasklines[0]:
        abort(404)
    queue = Queue(user.id)
    db.session.add(queue)
    db.session.commit()
    for taskline in tasklines:
        label, token = taskline.split()
        task = Task(queue.id, token, label)
        db.session.add(task)
    db.session.commit()
    return url_for('get', usertoken=user.token, queueid=queue.id, _external=True)


@app.route('/user/<username>/queue/<queueid>')
@authenticated
def queue(user, queueid):
    queue = Queue.query.get_or_404(int(queueid))
    rows = [(task.label, task.token, task.state, task.date_changed_str,
             task.caller or '')
            for task in queue.tasks.order_by(Task.id).all()]
    return render_template('queue.html',
                           username=user.name, queueid=queue.id, tasks=rows)


@app.route('/token/<usertoken>/queue/<queueid>/get')
@authenticated
def get(user, queueid):
    queue = Queue.query.get_or_404(int(queueid))
    task = queue.tasks.filter_by(state='Waiting').order_by(Task.id).first_or_404()
    caller = request.args.get('caller')
    task.change_state('Assigned', caller=caller)
    db.session.commit()
    return '\n'.join([
        task.token,
        task.label,
        url_for('change_state',
                usertoken=user.token, queueid=queueid, token=task.token,
                _external=True),
        url_for('put_back',
                usertoken=user.token, queueid=queueid, token=task.token,
                _external=True)
    ])


@app.route('/user/<username>/queue/<queueid>/reset')
@authenticated
def reset(user, queueid):
    queue = Queue.query.get_or_404(int(queueid))
    queue.tasks.filter(Task.state != 'Done').update({'state': 'Waiting'})
    db.session.commit()
    return redirect(url_for('user', username=user.name))


@app.route('/user/<username>/queue/<queueid>/reset-error')
@authenticated
def reset_error(user, queueid):
    queue = Queue.query.get_or_404(int(queueid))
    queue.tasks.filter(Task.state == 'Error').update({'state': 'Waiting'})
    db.session.commit()
    return redirect(url_for('user', username=user.name))


@app.route('/user/<username>/queue/<queueid>/delete')
@authenticated
def delete(user, queueid):
    queue = Queue.query.get_or_404(int(queueid))
    for task in queue.tasks:
        db.session.delete(task)
    db.session.delete(queue)
    db.session.commit()
    return redirect(url_for('user', username=user.name))


@app.route('/token/<usertoken>/queue/<queueid>/change_state/<path:token>')
@authenticated
def change_state(user, queueid, token):
    queue = Queue.query.get_or_404(int(queueid))
    task = queue.tasks.filter_by(token=token).first_or_404()
    state = request.args.get('state')
    task.change_state(state)
    db.session.commit()
    if queue.tasks.filter(Task.state.in_(['Waiting', 'Assigned'])).first() is None:
        queue.done = True
        db.session.commit()
        if user.pushover:
            pushover(user.pushover, 'Queue #{} is done'.format(queue.id))
    return ''


@app.route('/token/<usertoken>/queue/<queueid>/put_back/<path:token>')
@authenticated
def put_back(user, queueid, token):
    queue = Queue.query.get_or_404(int(queueid))
    task = queue.tasks.filter_by(token=token).first_or_404()
    db.session.delete(task)
    db.session.add(Task(queue.id, task.token, task.label, 'Waiting'))
    db.session.commit()
    return ''


if __name__ == '__main__':
    app.run(debug=True)
