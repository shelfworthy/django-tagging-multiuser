"""
Models and managers for generic tagging.
"""
# Python 2.3 compatibility
try:
    set
except NameError:
    from sets import Set as set

from django.conf import settings
from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.db import connection, models
from django.db.models.query import QuerySet
from django.utils.translation import ugettext_lazy as _

from tagging import settings
from tagging.utils import calculate_cloud, get_tag_list, get_queryset_and_model, parse_tag_input
from tagging.utils import LOGARITHMIC, unique_from_iter

if hasattr(settings, 'OWNER_MODEL') and settings.OWNER_MODEL:
    OWNER_MODEL = settings.OWNER_MODEL
else:
    from django.contrib.auth.models import User
    OWNER_MODEL = User

qn = connection.ops.quote_name




############
# Managers #
############

class TagManager(models.Manager):

    def update_tags(self, obj, tag_names, owner):
        """
        Update tags associated with an object.
        """
        ctype = ContentType.objects.get_for_model(obj)
        current_tags = list(self.filter(items__content_type__pk=ctype.pk,
                                        items__owners=owner,
                                        items__object_id=obj.pk))
        updated_tag_names = parse_tag_input(tag_names)
        if settings.FORCE_LOWERCASE_TAGS:
            updated_tag_names = [t.lower() for t in updated_tag_names]

        # Remove tags which no longer apply
        tags_for_removal = [tag for tag in current_tags \
                            if tag.name not in updated_tag_names]
        if len(tags_for_removal):
            items = TaggedItem._default_manager.filter(content_type__pk=ctype.pk,
                                                       object_id=obj.pk,
                                                       tag__in=tags_for_removal)
            for tag in tags_for_removal:
                if TaggedItem._default_manager.filter(owners=owner, content_type=ctype, object_id=tag.pk).count() <= 1:
                    tag.owners.remove(owner)
                    tag.save()

            for item in items:
                # remove the owner from the list
                item.owners.remove(owner)
                # if no one is using this tag anymore, remove it
                if item.owners.all().count():
                    item.save()
                else:
                    item.delete()

        # Add new tags
        current_tag_names = [tag.name for tag in current_tags]
        for tag_name in updated_tag_names:
            if tag_name not in current_tag_names:
                tag, created = self.get_or_create(name=tag_name)

                if owner not in tag.owners.all():
                    tag.owners.add(owner)
                    tag.save()

                t_item, created = TaggedItem._default_manager.get_or_create(tag=tag, object_id=obj.pk, content_type=ctype)
                t_item.owners.add(owner)
                t_item.save()


    def add_tag(self, obj, tag_name, owner):
        """
        Associates the given object with a tag.
        """
        tag_names = parse_tag_input(tag_name)
        if not len(tag_names):
            raise AttributeError(_('No tags were given: "%s".') % tag_name)
        if len(tag_names) > 1:
            raise AttributeError(_('Multiple tags were given: "%s".') % tag_name)
        tag_name = tag_names[0]
        if settings.FORCE_LOWERCASE_TAGS:
            tag_name = tag_name.lower()
        tag, created = self.get_or_create(name=tag_name)
        
        if owner not in tag.owners.all():
            tag.owners.add(owner)
            tag.save()

        ctype = ContentType.objects.get_for_model(obj)
        t_item, created = TaggedItem._default_manager.get_or_create(tag=tag, content_type=ctype, object_id=obj.pk)
        t_item.owners.add(owner)
        t_item.save()

    def get_for_object_owner(self, obj, owner):
        """
        Create a queryset matching all tags associated with the given
        object and owner.
        """
        return self.get_for_object(obj, owner, items__owners=owner)
 
    def get_for_model(self, model, owner_mark=None, *filter_args, **filter_kwargs):
        """
        Create a queryset matching the popular tags associated with the given
        object.
        """

        ctype = ContentType.objects.get_for_model(model)

        extra_select = {'popular': 'tagging_taggeditem.popular'} 
        select_params = []

        if owner_mark is not None:
            extra_select['is_own'] = '(SELECT COUNT(*) > 0 from tagging_taggeditem_owners WHERE taggeditem_id = tagging_taggeditem.id AND user_id = %s)'
            select_params.append(owner_mark.pk)
        
        filter_kwargs['items__content_type'] = ctype

        return self.select_related().filter(*filter_args, 
                **filter_kwargs).extra(select=extra_select, select_params=select_params).distinct()
                        # distinct is fail-safe hack for prevent wrong result when django creates 
                        # additional join when you try to make another .filter(items__ ... ) call

    def get_for_object(self, obj, owner_mark=None, *filter_args, **filter_kwargs):

        filter_kwargs['items__object_id'] = obj.pk
        
        return self.get_for_model(obj, owner_mark, *filter_args, **filter_kwargs)

    def get_for_owner(self, owner):

        return self.filter(items__owners=owner).distinct('pk')


    

class TaggedItemManager(models.Manager):
    """
    """

    def _get_matching_ids(self, model, tags, filter_function=None):
        
        if filter_function is None:
            filter_function = lambda item: True
    
        assert callable(filter_function)

        for tag in tags.select_related(depth=1):
            for item in tag.items.all():
                if item.object_id and filter_function(item):
                    yield item.object_id
    

    def match_any(self, model, tags, user_filter_function=None):

        ctype = ContentType.objects.get_for_model(model)
        
        default_filter = lambda item: item.content_type==ctype

        if user_filter_function is not None:
            filter_function = lambda item: (user_filter_function(item) and default_filter(item))
        else:
            filter_function = default_filter       

        ids = self._get_matching_ids(model, tags, filter_function)
        return model._default_manager.filter(pk__in=unique_from_iter(ids))


    def match_all(self, model, tags, user_filter_function=None):

        ctype = ContentType.objects.get_for_model(model)

        default_filter = lambda item: item.content_type==ctype

        if user_filter_function is not None:
            filter_function = lambda item: (user_filter_function(item) and default_filter(item))
        else:
            filter_function = default_filter

        ids = list(self._get_matching_ids(model, tags, filter_function))
        tag_len = isinstance(tags, models.query.QuerySet) and tags.count() or len(tags) 
        match_all_ids = [id for id in unique_from_iter(ids) if ids.count(id) == tag_len]

        if len(match_all_ids) == 0:
            return model._default_manager.none()

        return model._default_manager.filter(pk__in=match_all_ids)


##########
# Models # 
##########

class Tag(models.Model):
    """
    A tag.
    """
    name = models.CharField(_('name'), max_length=50, unique=True, db_index=True)
    owners       = models.ManyToManyField(OWNER_MODEL)
    objects = TagManager()

    class Meta:
        ordering = ('name',)
        verbose_name = _('tag')
        verbose_name_plural = _('tags')

    def __unicode__(self):
        return self.name

class TaggedItem(models.Model):
    """
    Holds the relationship between a tag, the item being tagged and the user doing the tagging.
    """
    owners       = models.ManyToManyField(OWNER_MODEL)
    tag          = models.ForeignKey(Tag, verbose_name=_('tag'), related_name='items')
    content_type = models.ForeignKey(ContentType, verbose_name=_('content type'))
    object_id    = models.PositiveIntegerField(_('object id'), db_index=True)
    object       = generic.GenericForeignKey('content_type', 'object_id')
    popular      = models.BooleanField(_('popular'))
    object_id    = models.PositiveIntegerField(_('object id'), db_index=True)

    objects = TaggedItemManager()

    class Meta:
        # Enforce unique tag association per object
        unique_together = (('tag', 'content_type', 'object_id',),)
        verbose_name = _('tagged item')
        verbose_name_plural = _('tagged items')

    def __unicode__(self):
        return u'%s [%s]' % (self.object, self.tag)

    def save(self, *args, **kwargs):

        # cannot work with ManyToMany if model is not created
        
        item = super(TaggedItem, self).save(*args, **kwargs)

        TaggedItem.refresh_popular(self.content_type, self.object_id)

        return item

    @staticmethod
    def refresh_popular(content_type, object_id):

        try:
            from .settings import MIN_OWNERS_COUNT_PER_TAG
        except ImportError:
            MIN_OWNERS_COUNT_PER_TAG = 0
        
        queryset = TaggedItem.objects.filter(content_type=content_type, object_id=object_id)

        tag_count = queryset.count()
        total_owners_count = queryset.aggregate(models.Count('owners'))['owners__count']
        avg = total_owners_count/tag_count
        
        if avg < MIN_OWNERS_COUNT_PER_TAG:
            avg = MIN_OWNERS_COUNT_PER_TAG

        popular_ids = [item['pk'] for item in queryset.annotate(oc=models.Count('owners')).filter(oc__gt=avg).values('pk')]

        queryset.exclude(pk__in=popular_ids).update(popular=False)
        queryset.filter(pk__in=popular_ids).update(popular=True)
        
        
        
        
        
