#!/usr/bin/env python3
import os,sys
proj=os.getcwd()
if proj not in sys.path: sys.path.insert(0,proj)
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from quotation.models import QuotationSection,QuotationSectionImage
qsec=QuotationSection.objects.filter(pk=88).first()
print('section pk=', qsec.pk if qsec else None)
imgs=list(QuotationSectionImage.objects.filter(section=qsec))
print('db count=', len(imgs))
for im in imgs:
    print(' -', im.image.name)
