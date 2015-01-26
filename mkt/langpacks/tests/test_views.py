# -*- coding: utf-8 -*-
import json

from django.core.urlresolvers import reverse
from django.forms import ValidationError

from mock import patch
from nose.tools import eq_, ok_

from mkt.api.tests.test_oauth import RestOAuth
from mkt.files.models import FileUpload
from mkt.langpacks.models import LangPack
from mkt.langpacks.tests.test_models import UploadCreationMixin, UploadTest
from mkt.site.fixtures import fixture
from mkt.users.models import UserProfile


class TestLangPackViewSetMixin(RestOAuth):
    fixtures = fixture('user_2519')

    def setUp(self):
        super(TestLangPackViewSetMixin, self).setUp()
        self.list_url = reverse('api-v2:langpack-list')
        self.user = UserProfile.objects.get(pk=2519)

    def create_langpack(self, **kwargs):
        data = {
            'filename': 'dummy.zip',
            'hash': 'dummy-hash',
            'size': 666,
            'active': True,
            'version': '0.1',
            'language': 'fr',
            'fxos_version': '2.2',
        }
        data.update(kwargs)
        return LangPack.objects.create(**data)

    def check_langpack(self, langpack_data, instance=None):
        if instance is None:
            instance = self.langpack
        eq_(instance.pk, langpack_data['uuid'])
        # FIXME: To implement in bug 1122279, don't expose the filename, expose
        # the minifest_url instead.
        eq_(instance.filename, langpack_data['filename'])
        eq_(instance.hash, langpack_data['hash'])
        eq_(instance.size, langpack_data['size'])
        eq_(instance.active, langpack_data['active'])
        eq_(instance.language, langpack_data['language'])
        eq_(instance.fxos_version, langpack_data['fxos_version'])


class TestLangPackViewSetBase(TestLangPackViewSetMixin):
    def setUp(self):
        super(TestLangPackViewSetBase, self).setUp()
        self.detail_url = reverse('api-v2:langpack-detail', kwargs={'pk': 42})

    def test_cors(self):
        self.assertCORS(self.anon.options(self.detail_url),
                        'get', 'delete', 'patch', 'post', 'put')
        self.assertCORS(self.anon.options(self.list_url),
                        'get', 'delete', 'patch', 'post', 'put')

    def test_no_double_slash(self):
        ok_(not self.detail_url.endswith('//'))
        ok_(not self.list_url.endswith('//'))


class TestLangPackViewSetGet(TestLangPackViewSetMixin):
    fixtures = fixture('user_2519')

    def setUp(self):
        super(TestLangPackViewSetGet, self).setUp()
        self.langpack = self.create_langpack()
        self.detail_url = reverse('api-v2:langpack-detail',
                                  kwargs={'pk': self.langpack.pk})

    # Anonymously, you can view all active langpacks.
    # Logged in view the right permission ('LangPacks', '%') you get them
    # all if you use active=0.

    def test_list_active(self):
        response = self.anon.get(self.list_url)
        eq_(response.status_code, 200)
        ok_(len(response.json['objects']), 1)
        self.check_langpack(response.json['objects'][0])

        response = self.client.get(self.list_url)
        eq_(response.status_code, 200)
        ok_(len(response.json['objects']), 1)
        self.check_langpack(response.json['objects'][0])

        response = self.client.get(self.list_url)
        eq_(response.status_code, 200)
        ok_(len(response.json['objects']), 1)
        self.check_langpack(response.json['objects'][0])

    def test_list_inactive_anon(self):
        self.create_langpack(active=False)
        response = self.anon.get(self.list_url, {'active': 'false'})
        eq_(response.status_code, 403)

    def test_list_inactive_no_perm(self):
        self.create_langpack(active=False)
        response = self.client.get(self.list_url, {'active': 'false'})
        eq_(response.status_code, 403)

    def test_list_inactive_has_perm(self):
        inactive_langpack = self.create_langpack(active=False)
        self.grant_permission(self.user, 'LangPacks:%')
        response = self.client.get(self.list_url, {'active': 'false'})
        eq_(response.status_code, 200)
        ok_(len(response.json['objects']), 1)
        self.check_langpack(response.json['objects'][0],
                            instance=inactive_langpack)

    def test_list_all_has_perm(self):
        inactive_langpack = self.create_langpack(active=False)
        inactive_langpack.update(created=self.days_ago(1))
        self.grant_permission(self.user, 'LangPacks:%')
        response = self.client.get(self.list_url, {'active': 'null'})
        eq_(response.status_code, 200)
        ok_(len(response.json['objects']), 2)
        self.check_langpack(response.json['objects'][0],
                            instance=self.langpack)
        self.check_langpack(response.json['objects'][1],
                            instance=inactive_langpack)

    def test_active_detail(self):
        response = self.anon.get(self.detail_url)
        eq_(response.status_code, 200)
        self.check_langpack(response.json)

        response = self.client.get(self.detail_url)
        eq_(response.status_code, 200)
        self.check_langpack(response.json)

    def test_inactive_detail_anon(self):
        self.langpack.update(active=False)
        response = self.anon.get(self.detail_url)
        eq_(response.status_code, 404)

    def test_inactive_detail_no_perm(self):
        self.langpack.update(active=False)
        response = self.client.get(self.detail_url)
        eq_(response.status_code, 404)

    def test_inactive_has_perm(self):
        self.langpack.update(active=False)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.get(self.detail_url)
        eq_(response.status_code, 200)
        self.check_langpack(response.json)


class TestLangPackViewSetCreate(TestLangPackViewSetMixin, UploadCreationMixin,
                                UploadTest):
    def test_anonymous(self):
        response = self.anon.post(self.list_url)
        eq_(response.status_code, 403)

    def test_no_perms(self):
        response = self.client.post(self.list_url)
        eq_(response.status_code, 403)

    @patch('mkt.langpacks.serializers.LangPackUploadSerializer.is_valid',
           return_value=True)
    @patch('mkt.langpacks.serializers.LangPackUploadSerializer.save',
           return_value=None)
    def test_with_perm(self, mock_save, mock_is_valid):
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.post(self.list_url)
        eq_(response.status_code, 201)

    def test_no_upload(self):
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.post(self.list_url)
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'This field is required.']})

    def test_upload_does_not_exist(self):
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.post(self.list_url, data=json.dumps({
            'upload': 'my-non-existing-uuid'}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'No upload found.']})

    def test_dont_own_the_upload(self):
        FileUpload.objects.create(uuid='my-uuid', user=None, valid=True)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.post(self.list_url, data=json.dumps({
            'upload': 'my-uuid'}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'No upload found.']})

    def test_invalid_upload(self):
        FileUpload.objects.create(uuid='my-uuid', valid=False, user=self.user)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.post(self.list_url, data=json.dumps({
            'upload': 'my-uuid'}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'Upload not valid.']})

    @patch('mkt.langpacks.models.LangPack.from_upload')
    def test_errors_returned_by_from_upload(self, mock_from_upload):
        mock_from_upload.side_effect = ValidationError('foo bar')
        FileUpload.objects.create(uuid='my-uuid', valid=True, user=self.user)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.post(self.list_url, data=json.dumps({
            'upload': 'my-uuid'}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'detail': [u'foo bar']})

    def test_create(self):
        eq_(LangPack.objects.count(), 0)
        upload = self.upload('langpack.zip', valid=True, user=self.user)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.post(self.list_url, data=json.dumps({
            'upload': upload.uuid}))
        eq_(response.status_code, 201)
        eq_(LangPack.objects.count(), 1)
        langpack = LangPack.objects.get()
        eq_(langpack.hash[0:23], 'sha256:f0fa5a4f5c0edf2d')
        eq_(langpack.size, 499)
        eq_(langpack.active, False)
        eq_(response.data['uuid'], langpack.uuid)
        eq_(response.data['hash'], langpack.hash)
        eq_(response.data['active'], langpack.active)

    def test_create_with_existing_langpack_in_db(self):
        self.langpack = self.create_langpack()
        eq_(LangPack.objects.count(), 1)
        upload = self.upload('langpack.zip', valid=True, user=self.user)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.post(self.list_url, data=json.dumps({
            'upload': upload.uuid}))
        eq_(response.status_code, 201)
        ok_(response.json['uuid'] != self.langpack.pk)
        eq_(LangPack.objects.count(), 2)
        langpack = LangPack.objects.get(pk=response.json['uuid'])
        eq_(langpack.hash[0:23], 'sha256:f0fa5a4f5c0edf2d')
        eq_(langpack.size, 499)
        eq_(langpack.active, False)
        eq_(langpack.language, 'de')
        eq_(langpack.fxos_version, '2.2')
        eq_(response.data['uuid'], langpack.uuid)
        eq_(response.data['hash'], langpack.hash)
        eq_(response.data['active'], langpack.active)


class TestLangPackViewSetUpdate(TestLangPackViewSetMixin, UploadCreationMixin, UploadTest):
    def setUp(self):
        super(TestLangPackViewSetUpdate, self).setUp()
        self.langpack = self.create_langpack()
        self.detail_url = reverse('api-v2:langpack-detail',
                                  kwargs={'pk': self.langpack.pk})
    def test_anonymous(self):
        response = self.anon.put(self.detail_url)
        eq_(response.status_code, 403)

    def test_no_perms(self):
        response = self.client.put(self.detail_url)
        eq_(response.status_code, 403)

    @patch('mkt.langpacks.serializers.LangPackUploadSerializer.is_valid',
           return_value=True)
    @patch('mkt.langpacks.serializers.LangPackUploadSerializer.save',
           return_value=None)
    def test_with_perm(self, mock_save, mock_is_valid):
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.put(self.detail_url)
        eq_(response.status_code, 200)

    def test_no_upload(self):
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.put(self.detail_url)
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'This field is required.']})

    def test_upload_does_not_exist(self):
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.put(self.detail_url, data=json.dumps({
            'upload': 'my-non-existing-uuid'}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'No upload found.']})

    def test_dont_own_the_upload(self):
        FileUpload.objects.create(uuid='my-uuid', user=None, valid=True)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.put(self.detail_url, data=json.dumps({
            'upload': 'my-uuid'}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'No upload found.']})

    def test_invalid_upload(self):
        FileUpload.objects.create(uuid='my-uuid', valid=False, user=self.user)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.put(self.detail_url, data=json.dumps({
            'upload': 'my-uuid'}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'upload': [u'Upload not valid.']})

    @patch('mkt.langpacks.models.LangPack.from_upload')
    def test_errors_returned_by_from_upload(self, mock_from_upload):
        mock_from_upload.side_effect = ValidationError('foo bar')
        FileUpload.objects.create(uuid='my-uuid', valid=True, user=self.user)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.put(self.detail_url, data=json.dumps({
            'upload': 'my-uuid'}))
        eq_(response.status_code, 400)
        eq_(response.json, {u'detail': [u'foo bar']})

    def test_update(self):
        upload = self.upload('langpack.zip', valid=True, user=self.user)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.put(self.detail_url, data=json.dumps({
            'upload': upload.uuid}))
        eq_(response.status_code, 200)
        eq_(LangPack.objects.count(), 1)
        langpack = LangPack.objects.get()
        eq_(langpack.hash[0:23], 'sha256:f0fa5a4f5c0edf2d')
        eq_(langpack.size, 499)
        eq_(langpack.active, True)  # Langpack was already active.
        eq_(langpack.language, 'de')
        eq_(langpack.fxos_version, '2.2')
        eq_(response.data['uuid'], langpack.uuid)
        eq_(response.data['hash'], langpack.hash)
        eq_(response.data['active'], langpack.active)

    def test_update_with_another_existing_langpack_in_db(self):
        self.langpack = self.create_langpack()
        eq_(LangPack.objects.count(), 2)
        upload = self.upload('langpack.zip', valid=True, user=self.user)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.put(self.detail_url, data=json.dumps({
            'upload': upload.uuid}))
        eq_(response.status_code, 200)
        eq_(LangPack.objects.count(), 2)
        langpack = LangPack.objects.get(pk=response.json['uuid'])
        eq_(langpack.hash[0:23], 'sha256:f0fa5a4f5c0edf2d')
        eq_(langpack.size, 499)
        eq_(langpack.active, True)
        eq_(langpack.language, 'de')
        eq_(langpack.fxos_version, '2.2')
        eq_(response.data['uuid'], langpack.uuid)
        eq_(response.data['hash'], langpack.hash)
        eq_(response.data['active'], langpack.active)

    def test_update_was_inactive(self):
        self.langpack.update(active=False)
        upload = self.upload('langpack.zip', valid=True, user=self.user)
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.put(self.detail_url, data=json.dumps({
            'upload': upload.uuid}))
        eq_(response.status_code, 200)
        eq_(LangPack.objects.count(), 1)
        langpack = LangPack.objects.get()
        eq_(langpack.hash[0:23], 'sha256:f0fa5a4f5c0edf2d')
        eq_(langpack.size, 499)
        eq_(langpack.active, False)
        eq_(langpack.language, 'de')
        eq_(langpack.fxos_version, '2.2')
        eq_(response.data['uuid'], langpack.uuid)
        eq_(response.data['hash'], langpack.hash)
        eq_(response.data['active'], langpack.active)


class TestLangPackViewSetPartialUpdate(TestLangPackViewSetMixin):
    def setUp(self):
        super(TestLangPackViewSetPartialUpdate, self).setUp()
        self.langpack = self.create_langpack()
        self.detail_url = reverse('api-v2:langpack-detail',
                                  kwargs={'pk': self.langpack.pk})

    def test_anonymous(self):
        response = self.anon.patch(self.detail_url)
        eq_(response.status_code, 403)

    def test_no_perms(self):
        response = self.client.patch(self.detail_url)
        eq_(response.status_code, 403)

    def test_with_perm(self):
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.patch(self.detail_url,
                                     json.dumps({'active': False}))
        eq_(response.status_code, 200)
        eq_(response.data['active'], False)
        self.langpack.reload()
        eq_(self.langpack.pk, response.data['uuid'])
        eq_(self.langpack.active, response.data['active'])

    def test_not_allowed_fields(self):
        self.grant_permission(self.user, 'LangPacks:%')

        response = self.client.patch(self.detail_url, json.dumps({
            'active': False,
            'filename': 'dummy-data',
            'fxos_version': 'dummy-data',
            'hash': 'dummy-data',
            'language': 'es',
            'modified': 'dummy-data',
            'size': 666,
            'uuid': 'dummy-data',
            'version': 'dummy-data',
        }))
        eq_(response.status_code, 400)
        eq_(response.data, {
            'hash': [u'This field is read-only.'],
            'language': [u'This field is read-only.'],
            'fxos_version': [u'This field is read-only.'],
            'filename': [u'This field is read-only.'],
            'version': [u'This field is read-only.'],
            'size': [u'This field is read-only.']})
        self.langpack.reload()
        eq_(self.langpack.active, True)  # Not changed.
