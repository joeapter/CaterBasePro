import csv
from decimal import Decimal
from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path

from .models import CatererAccount, MenuItem, MenuCategory, ExtraItem
