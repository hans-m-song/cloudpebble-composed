from social.backends.oauth import BaseOAuth2
from django.conf import settings
from ide.models.user import UserGithub
from ide.models.project import Project
#import ide.utils.mailinglist as mailinglist

class PebbleOAuth2(BaseOAuth2):
    name = 'pebble'
    AUTHORIZATION_URL = '{0}/oauth/authorise'.format(settings.SOCIAL_AUTH_PEBBLE_ROOT_URL)
    ACCESS_TOKEN_URL = '{0}/oauth/token'.format(settings.SOCIAL_AUTH_PEBBLE_ROOT_URL)
    ACCESS_TOKEN_METHOD = 'POST'
    STATE_PARAMETER = 'state'
    DEFAULT_SCOPE = ['profile']
    REDIRECT_STATE = False
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_SAMESITE = None
    ID_KEY = 'uid'
    #SOCIAL_AUTH_LOGIN_REDIRECT_URL 'http://cloudpebble.tk/complete/pebble/'
    SOCIAL_AUTH_REDIRECT_IS_HTTPS = False
    SOCIAL_AUTH_FIELDS_STORED_IN_SESSION = ['state']
    LOGIN_REDIRECT_URL = '/ide/'

    def auth_by_token(request, backend):
    	"""Decorator that creates/authenticates a user with an access_token"""
    	token = request.DATA.get('access_token')
    	user = request.user
    	user = request.backend.do_auth(
            access_token=request.DATA.get('access_token')
        )
    	if user:
        	return user
    	else:
        	return None

    def post(self, request, format=None):
        auth_token = request.DATA.get('access_token', None)
        backend = request.DATA.get('backend', None)
        if auth_token and backend:
            try:
                # Try to authenticate the user using python-social-auth
                user = auth_by_token(request, backend)
            except Exception,e:
                return Response({
                        'status': 'Bad request',
                        'message': 'Could not authenticate with the provided token.'
                    }, status=status.HTTP_400_BAD_REQUEST)
            if user:
                if not user.is_active:
                    return Response({
                        'status': 'Unauthorized',
                        'message': 'The user account is disabled.'
                    }, status=status.HTTP_401_UNAUTHORIZED)

                # This is the part that differs from the normal python-social-auth implementation.
                # Return the JWT instead.

                # Get the JWT payload for the user.
                payload = jwt_payload_handler(user)

                # Include original issued at time for a brand new token,
                # to allow token refresh
                if api_settings.JWT_ALLOW_REFRESH:
                    payload['orig_iat'] = timegm(
                        datetime.utcnow().utctimetuple()
                    )

                # Create the response object with the JWT payload.
                response_data = {
                    'token': jwt_encode_handler(payload)
                }

                return Response(response_data)
        else:
            return Response({
                    'status': 'Bad request',
                    'message': 'Authentication could not be performed with received data.'
            }, status=status.HTTP_400_BAD_REQUEST)

    def get_user_details(self, response):
        return {
            'email': response.get('email'),
            'fullname': response.get('name'),
            'username': response.get('user.id'),
            'uid': response.get('uid')
        }

    def user_data(self, access_token, *args, **kwargs):
        url = '{0}/api/v1/me'.format(settings.SOCIAL_AUTH_PEBBLE_ROOT_URL)
        return self.get_json(
            url,
            headers={'Authorization': 'Bearer {0}'.format(access_token)}
        )

def merge_user(strategy, uid, user=None, *args, **kwargs):
    provider = strategy.backend.name
    social = strategy.storage.user.get_social_auth(provider, uid)
    if social:
        if user and social.user != user:
            # msg = 'This {0} account is already in use.'.format(provider)
            # raise AuthAlreadyAssociated(strategy.backend, msg)
            # Try merging the users.
            # Do this first, simply because it's both most important and most likely to fail.
            Project.objects.filter(owner=social.user).update(owner=user)
            # If one user has GitHub settings and the other doesn't, use them.
            try:
                github = UserGithub.objects.get(user=social.user)
                if github:
                    if UserGithub.objects.filter(user=user).count() == 0:
                        github.user = user
                        github.save()
            except UserGithub.DoesNotExist:
                pass
            # Delete our old social user.
            social.user.delete()
            social = None

        elif not user:
            user = social.user
            #mailinglist.add_user(user)
    return {'social': social,
            'user': user,
            'is_new': user is None,
            'new_association': False}

def clear_old_login(strategy, uid, user=None, *args, **kwargs):
    provider = strategy.backend.name
    social = strategy.storage.user.get_social_auth(provider, uid)
    if user and social and user == social.user:
        if user.has_usable_password():
            user.set_unusable_password()