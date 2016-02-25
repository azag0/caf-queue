from flask import Flask, request, abort
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///{}/queue.db'.format(app.root_path)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(20), unique=True)
    queues = db.relationship('Queue', backref='user', lazy='dynamic')

    def __init__(self, token):
        self.token = token


class Queue(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    tasks = db.relationship('Task', backref='queue', lazy='dynamic')

    def __init__(self, user_id):
        self.user_id = user_id


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    queue_id = db.Column(db.Integer, db.ForeignKey('queue.id'))
    token = db.Column(db.String(50))

    def __init__(self, queue_id, token):
        self.queue_id = queue_id
        self.token = token


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
    return str('/get/{}/{}'.format(user.token, queue.id))


@app.route('/get/<user>/<queue>')
def get(user, queue):
    User.query.filter_by(token=user).first_or_404()
    queue = Queue.query.get_or_404(int(queue))
    task = queue.tasks.first()
    if task is None:
        db.session.delete(queue)
        db.session.commit()
        abort(404)
    db.session.delete(task)
    db.session.commit()
    return task.token


if __name__ == '__main__':
    app.run(debug=True)
