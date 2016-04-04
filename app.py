from flask import Flask, request, url_for
from flask_sqlalchemy import SQLAlchemy
import http.client
import urllib


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///{}/queue.db'.format(app.root_path)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


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


class Pushover(db.Model):
    token = db.Column(db.String(20), primary_key=True)

    def __init__(self, token):
        self.token = token


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(20), unique=True)
    pushover = db.Column(db.String(20))
    queues = db.relationship('Queue', backref='user', lazy='dynamic')

    def __init__(self, token, pushover=None):
        self.token = token
        self.pushover = pushover


class Queue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    tasks = db.relationship('Task', backref='queue', lazy='dynamic')

    def __init__(self, user_id):
        self.user_id = user_id


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    queue_id = db.Column(db.Integer, db.ForeignKey('queue.id'))
    assigned = db.Column(db.Boolean)
    token = db.Column(db.String(50))

    def __init__(self, queue_id, token):
        self.queue_id = queue_id
        self.token = token
        self.assigned = False
        self.done = False


@app.route('/submit/<user>', methods=['POST'])
def submit(user):
    if request.method == 'POST':
        user = User.query.filter_by(token=user).first_or_404()
        tasks = request.get_data().decode().split()
        queue = Queue(user.id)
        db.session.add(queue)
        db.session.commit()
        for task in tasks:
            task = Task(queue.id, task)
            db.session.add(task)
        db.session.commit()
    return url_for('get', user=user.token, queue=queue.id,
                   _external=True)


@app.route('/get/<user>/<queue>')
def get(user, queue):
    User.query.filter_by(token=user).first_or_404()
    queue = Queue.query.get_or_404(int(queue))
    task = queue.tasks.filter_by(assigned=False).order_by(Task.id).first_or_404()
    task.assigned = True
    db.session.commit()
    return '{}\n{}'.format(
        task.token,
        url_for('done', user=user, queue=queue.id, task=task.token,
                _external=True))


@app.route('/done/<user>/<queue>/<path:task>')
def done(user, queue, task):
    user = User.query.filter_by(token=user).first_or_404()
    queue = Queue.query.get_or_404(int(queue))
    task = queue.tasks.filter_by(token=task).first_or_404()
    db.session.delete(task)
    db.session.commit()
    if queue.tasks.first() is None:
        db.session.delete(queue)
        db.session.commit()
        if user.pushover:
            pushover(user.pushover,
                     'Queue #{} is done'.format(queue.id))
    return ''


@app.route('/reset/<user>/<queue>')
def reset(user, queue):
    User.query.filter_by(token=user).first_or_404()
    queue = Queue.query.get_or_404(int(queue))
    queue.tasks.update({'assigned': False})
    db.session.commit()
    return ''


if __name__ == '__main__':
    app.run(debug=True)
