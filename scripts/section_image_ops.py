#!/usr/bin/env python3
import os,sys
import argparse
proj=os.getcwd()
if proj not in sys.path: sys.path.insert(0,proj)
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.core.files import File
from quotation.models import QuotationSection,QuotationSectionImage

parser=argparse.ArgumentParser()
parser.add_argument('--action',choices=['list','clear','add','count'],required=True)
parser.add_argument('--section',type=int,default=88)
parser.add_argument('--file',help='path to source file for add')
args=parser.parse_args()
section=QuotationSection.objects.filter(pk=args.section).first()
if not section:
    print('section-missing')
    sys.exit(2)
if args.action in ('list','count'):
    imgs=list(QuotationSectionImage.objects.filter(section=section).order_by('pk'))
    if args.action=='count':
        print(len(imgs))
    else:
        print('section pk=',section.pk)
        print('db count=', len(imgs))
        for im in imgs:
            print('-', im.pk, im.image.name)
    sys.exit(0)
if args.action=='clear':
    imgs=list(QuotationSectionImage.objects.filter(section=section))
    for im in imgs:
        try:
            im.image.delete(save=False)
        except Exception:
            pass
        im.delete()
    print('cleared')
    sys.exit(0)
if args.action=='add':
    if not args.file:
        print('missing-file')
        sys.exit(3)
    if not os.path.exists(args.file):
        print('file-not-found')
        sys.exit(4)
    fname=os.path.basename(args.file)
    with open(args.file,'rb') as f:
        django_file=File(f)
        img=QuotationSectionImage(section=section)
        img.image.save(fname, django_file, save=True)
        print('added', img.pk, img.image.name)
    sys.exit(0)
