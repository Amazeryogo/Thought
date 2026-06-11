from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, PasswordField, BooleanField, SubmitField, MultipleFileField
from wtforms.validators import DataRequired, Email, EqualTo


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')


class CreateUserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Join Thought')


from wtforms import SelectField

class PostForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    content = TextAreaField('Content', validators=[DataRequired()])
    images = MultipleFileField('Images')
    visibility = SelectField('Visibility', choices=[('public', 'Public'), ('followers', 'Followers Only'), ('private', 'Private')])
    post_to = SelectField('Post To', choices=[('account', 'My Account')])
    is_poll = BooleanField('Create Poll')
    poll_options = StringField('Poll Options (comma separated)')
    is_draft = BooleanField('Save as Draft')
    submit = SubmitField('Post')


class SettingsForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    content = TextAreaField('About Me', validators=[DataRequired()])
    is_private = BooleanField('Private Account')
    submit = SubmitField('Update')


class RequestResetForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Request Password Reset')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password',
                                     validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Reset Password')


class CommentForm(FlaskForm):
    content = TextAreaField('Your Comment', validators=[DataRequired()], render_kw={"class": "form-control", "rows": 3})
    submit = SubmitField('Post Comment', render_kw={"class": "btn btn-primary mt-2"})


class MessageForm(FlaskForm):
    message = TextAreaField('Message', validators=[DataRequired()])
    submit = SubmitField('send')


class RepositoryForm(FlaskForm):
    name = StringField('Repository Name', validators=[DataRequired()])
    description = TextAreaField('Description')
    submit = SubmitField('Create Repository')
