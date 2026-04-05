"""
Shared test fixtures for CodeVault test suite.
"""
import pytest
from django.test import TestCase
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    from apps.accounts.models import User
    return User.objects.create_user(
        email='test@example.com',
        password='testpass123',
        name='Test User',
    )


@pytest.fixture
def auth_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def project(user, db):
    from apps.projects.models import Project
    return Project.objects.create(
        name='Test Project',
        slug='test-project',
        owner=user,
        language='python',
        local_path='/tmp/test-project',
    )


@pytest.fixture
def project_with_member(project, db):
    from apps.accounts.models import User
    from apps.projects.models import ProjectMember
    member_user = User.objects.create_user(
        email='member@example.com',
        password='testpass123',
        name='Member User',
    )
    membership = ProjectMember.objects.create(
        project=project,
        user=member_user,
        role='member',
    )
    return project, member_user, membership


# Sample source code fixtures for parser tests
PYTHON_SOURCE = b'''
import os
from django.db import models
from django.dispatch import receiver
from django.db.models.signals import post_save

class UserProfile(models.Model):
    """User profile extending the base User model."""
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE)
    bio = models.TextField(blank=True)
    avatar_url = models.URLField(blank=True)

    class Meta:
        verbose_name = 'User Profile'

    def get_display_name(self):
        """Return the user display name."""
        return self.user.get_full_name() or self.user.username

    async def fetch_avatar(self):
        """Fetch avatar from external service."""
        pass


def create_default_profile(user):
    """Create a default profile for new users."""
    return UserProfile.objects.create(user=user)


@receiver(post_save, sender='auth.User')
def auto_create_profile(sender, instance, created, **kwargs):
    if created:
        create_default_profile(instance)
'''

JS_SOURCE = b'''
import express from 'express';
import { UserService } from './services/user';

const router = express.Router();

/**
 * Get user by ID
 * @param {string} id - User ID
 * @returns {Object} User object
 */
async function getUserById(id) {
    return await UserService.findById(id);
}

const createUser = async (data) => {
    return await UserService.create(data);
};

class AuthController {
    async login(req, res) {
        const { email, password } = req.body;
        const token = await this.authenticate(email, password);
        res.json({ token });
    }
}

router.get('/users/:id', getUserById);
router.post('/users', createUser);

export default router;
'''

GO_SOURCE = b'''
package handlers

import (
    "encoding/json"
    "net/http"
)

// UserHandler handles user-related HTTP requests.
type UserHandler struct {
    Service *UserService
    Logger  *Logger
}

// User represents a user entity in the system.
type User struct {
    ID    int    `json:"id" db:"id"`
    Name  string `json:"name" db:"name"`
    Email string `json:"email" db:"email"`
}

// GetUser retrieves a user by ID.
func (h *UserHandler) GetUser(w http.ResponseWriter, r *http.Request) {
    id := r.URL.Query().Get("id")
    user, err := h.Service.FindByID(id)
    if err != nil {
        http.Error(w, err.Error(), 500)
        return
    }
    json.NewEncoder(w).Encode(user)
}

func CreateUser(w http.ResponseWriter, r *http.Request) {
    var user User
    json.NewDecoder(r.Body).Decode(&user)
    json.NewEncoder(w).Encode(user)
}
'''

RUST_SOURCE = b'''
use actix_web::{get, post, web, HttpResponse};
use serde::{Deserialize, Serialize};

/// A user entity
#[derive(Debug, Serialize, Deserialize)]
pub struct User {
    pub id: i64,
    pub name: String,
    pub email: String,
}

/// User service for database operations
pub trait UserRepository {
    fn find_by_id(&self, id: i64) -> Option<User>;
    fn create(&self, user: User) -> User;
}

impl UserService {
    /// Create a new user service instance
    pub fn new(pool: DbPool) -> Self {
        Self { pool }
    }

    pub async fn find_user(&self, id: i64) -> Result<User, Error> {
        todo!()
    }
}

#[get("/users/{id}")]
async fn get_user(path: web::Path<i64>) -> HttpResponse {
    HttpResponse::Ok().json(User { id: path.into_inner(), name: "test".into(), email: "test@test.com".into() })
}

#[post("/users")]
async fn create_user(body: web::Json<User>) -> HttpResponse {
    HttpResponse::Created().json(body.into_inner())
}
'''

JAVA_SOURCE = b'''
package com.example.controller;

import org.springframework.web.bind.annotation.*;
import org.springframework.beans.factory.annotation.Autowired;

/**
 * User REST controller
 */
@RestController
@RequestMapping("/api/users")
public class UserController {

    @Autowired
    private UserService userService;

    /**
     * Get user by ID
     */
    @GetMapping("/{id}")
    public User getUser(@PathVariable Long id) {
        return userService.findById(id);
    }

    @PostMapping
    public User createUser(@RequestBody User user) {
        return userService.save(user);
    }

    @DeleteMapping("/{id}")
    public void deleteUser(@PathVariable Long id) {
        userService.deleteById(id);
    }
}

public class User {
    private Long id;
    private String name;
    private String email;
}

public interface UserRepository extends JpaRepository<User, Long> {
    List<User> findByEmail(String email);
}
'''
