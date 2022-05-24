from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')


class CreateUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired()])
    submit = SubmitField('Create User')


class PostForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    content = TextAreaField('Content', validators=[DataRequired()])
    submit = SubmitField('Post')


class AboutMeForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired()])
    content = TextAreaField('aboutme', validators=[DataRequired()])
    submit = SubmitField('Update')


class ResetPasswordRequestForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired()])
    submit = SubmitField('Request Password Reset')


class ResetPasswordForm(FlaskForm):
    password = PasswordField('Password', validators=[DataRequired()])
    repeat = PasswordField(
        'Repeat Password', validators=[DataRequired()])
    submit = SubmitField('Please Reset my password')


class MessageForm(FlaskForm):
    message = TextAreaField('Message', validators=[DataRequired()])
    submit = SubmitField('send')
