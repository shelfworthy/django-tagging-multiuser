# -*- coding: utf-8 -*-
r"""
>>> import os
>>> from django import forms
>>> from django.db.models import Q
>>> from django.contrib.auth.models import User
>>> from tagging.forms import TagField
>>> from tagging import settings
>>> from tagging.models import Tag, TaggedItem
>>> from tagging.tests.models import Article, Link, Perch, Parrot
>>> from tagging.utils import calculate_cloud, get_tag_list, get_tag, parse_tag_input
>>> from tagging.utils import LINEAR

#############
# Utilities #
#############

# Tag input ###################################################################

# Simple space-delimited tags
>>> parse_tag_input('one')
[u'one']
>>> parse_tag_input('one two')
[u'one', u'two']
>>> parse_tag_input('one two three')
[u'one', u'three', u'two']
>>> parse_tag_input('one one two two')
[u'one', u'two']

# Comma-delimited multiple words - an unquoted comma in the input will trigger
# this.
>>> parse_tag_input(',one')
[u'one']
>>> parse_tag_input(',one two')
[u'one two']
>>> parse_tag_input(',one two three')
[u'one two three']
>>> parse_tag_input('a-one, a-two and a-three')
[u'a-one', u'a-two and a-three']

# Double-quoted multiple words - a completed quote will trigger this.
# Unclosed quotes are ignored.
>>> parse_tag_input('"one')
[u'one']
>>> parse_tag_input('"one two')
[u'one', u'two']
>>> parse_tag_input('"one two three')
[u'one', u'three', u'two']
>>> parse_tag_input('"one two"')
[u'one two']
>>> parse_tag_input('a-one "a-two and a-three"')
[u'a-one', u'a-two and a-three']

# No loose commas - split on spaces
>>> parse_tag_input('one two "thr,ee"')
[u'one', u'thr,ee', u'two']

# Loose commas - split on commas
>>> parse_tag_input('"one", two three')
[u'one', u'two three']

# Double quotes can contain commas
>>> parse_tag_input('a-one "a-two, and a-three"')
[u'a-one', u'a-two, and a-three']
>>> parse_tag_input('"two", one, one, two, "one"')
[u'one', u'two']

# Bad users! Naughty users!
>>> parse_tag_input(None)
[]
>>> parse_tag_input('')
[]
>>> parse_tag_input('"')
[]
>>> parse_tag_input('""')
[]
>>> parse_tag_input('"' * 7)
[]
>>> parse_tag_input(',,,,,,')
[]
>>> parse_tag_input('",",",",",",","')
[u',']
>>> parse_tag_input('a-one "a-two" and "a-three')
[u'a-one', u'a-three', u'a-two', u'and']

# Normalised Tag list input ###################################################
>>> cheese = Tag.objects.create(name='cheese')
>>> toast = Tag.objects.create(name='toast')
>>> get_tag_list(cheese)
[<Tag: cheese>]
>>> get_tag_list('cheese toast')
[<Tag: cheese>, <Tag: toast>]
>>> get_tag_list('cheese,toast')
[<Tag: cheese>, <Tag: toast>]
>>> get_tag_list([])
[]
>>> get_tag_list(['cheese', 'toast'])
[<Tag: cheese>, <Tag: toast>]
>>> get_tag_list([cheese.id, toast.id])
[<Tag: cheese>, <Tag: toast>]
>>> get_tag_list(['cheese', 'toast', 'ŠĐĆŽćžšđ'])
[<Tag: cheese>, <Tag: toast>]
>>> get_tag_list([cheese, toast])
[<Tag: cheese>, <Tag: toast>]
>>> get_tag_list((cheese, toast))
(<Tag: cheese>, <Tag: toast>)
>>> get_tag_list(Tag.objects.filter(name__in=['cheese', 'toast']))
[<Tag: cheese>, <Tag: toast>]
>>> get_tag_list(['cheese', toast])
Traceback (most recent call last):
    ...
ValueError: If a list or tuple of tags is provided, they must all be tag names, Tag objects or Tag ids.
>>> get_tag_list(29)
Traceback (most recent call last):
    ...
ValueError: The tag input given was invalid.

# Normalised Tag input
>>> get_tag(cheese)
<Tag: cheese>
>>> get_tag('cheese')
<Tag: cheese>
>>> get_tag(cheese.id)
<Tag: cheese>
>>> get_tag('mouse')

###########
# Tagging #
###########
>>> u1 = User.objects.create(username='tony')
>>> u2 = User.objects.create(username='geek')
>>> u3 = User.objects.create(username='blah')
>>> u4 = User.objects.create(username='atmta')
>>> dead = Parrot.objects.create(state='dead')
>>> alive = Parrot.objects.create(state='alive')
>>> Tag.objects.update_tags(dead, 'foo,bar,"ter"', u1)
>>> Tag.objects.get_for_object(dead)
[<Tag: bar>, <Tag: foo>, <Tag: ter>]
>>> Tag.objects.get_for_object_owner(dead, u1)
[<Tag: bar>, <Tag: foo>, <Tag: ter>]
>>> Tag.objects.update_tags(dead, '"foo" bar "baz"', u1)
>>> Tag.objects.get_for_object(dead)
[<Tag: bar>, <Tag: baz>, <Tag: foo>]
>>> Tag.objects.add_tag(dead, 'foo', u1)
>>> Tag.objects.get_for_object(dead)
[<Tag: bar>, <Tag: baz>, <Tag: foo>]
>>> Tag.objects.add_tag(dead, 'zip', u2)
>>> Tag.objects.get_for_object(dead)
[<Tag: bar>, <Tag: baz>, <Tag: foo>, <Tag: zip>]
>>> Tag.objects.add_tag(dead, '    ', u1)
Traceback (most recent call last):
    ...
AttributeError: No tags were given: "    ".
>>> Tag.objects.add_tag(dead, 'one two', u1)
Traceback (most recent call last):
    ...
AttributeError: Multiple tags were given: "one two".


>>> Tag.objects.get_for_object_owner(dead, u1)
[<Tag: bar>, <Tag: baz>, <Tag: foo>]
>>> Tag.objects.get_for_object_owner(dead, u2)
[<Tag: zip>]

>>> Tag.objects.update_tags(dead, None, u1)
>>> Tag.objects.get_for_object_owner(dead, u1)
[]

>>> Tag.objects.get_for_object(dead)
[<Tag: zip>]

>>> Tag.objects.update_tags(alive, 'bar ololo xxx zip', u2)
>>> Tag.objects.get_for_owner(u2)
[<Tag: bar>, <Tag: ololo>, <Tag: xxx>, <Tag: zip>]

################
# Popular Tags #
################


>>> TaggedItem.objects.filter(popular=True)
[]

>>> Tag.objects.update_tags(alive, 'bar zip', u1)
>>> Tag.objects.update_tags(alive, 'bar zip', u3)
>>> Tag.objects.update_tags(alive, 'bar zip', u4)

>>> [t for t in Tag.objects.get_for_object(alive) if t.popular == True]
[<Tag: bar>, <Tag: zip>]

###############
# TaggedItems #
###############

# simple with any
>>> Parrot.objects.with_any(Tag.objects.filter(name__in=('bar', 'zip')))
[<Parrot: alive>, <Parrot: dead>]

# by popular with any 
>>> Parrot.objects.with_any(Tag.objects.filter(name__in=('bar', 'zip')), lambda i: i.popular==True)
[<Parrot: alive>]

# simple with all
>>> Tag.objects.update_tags(dead, 'bar zip', u4)
>>> Parrot.objects.with_all(Tag.objects.filter(name__in=('bar', 'zip')))
[<Parrot: alive>, <Parrot: dead>]

>>> Parrot.objects.with_all(Tag.objects.filter(name__in=('bar', 'zip')), lambda i: i.popular==True)
[<Parrot: alive>]

"""
