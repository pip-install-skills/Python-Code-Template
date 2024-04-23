from fastapi import APIRouter, HTTPException, Depends, Request, status
from login import get_current_user, authorize_user, oauth2_scheme, User, create_access_token, Hash
from app.classes.dbconfig import user_data,db
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.security import OAuth2PasswordBearer


router = APIRouter()

@router.post('/register', dependencies=[Depends(authorize_user)])
def create_user(request: User, current_user:User = Depends(get_current_user),token: str = Depends(oauth2_scheme)):

    if current_user.get('role') != "Admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    existing_user = db["Users_data"].find_one({"username": request.username})
    print("request: ",request.username)
    print("existing user: ",existing_user)
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username " +request.username +" already taken")
    if not request.username or not request.password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request")   
    hashed_pass = Hash.bcrypt(request.password)
    user_object = dict(request)
    user_object["password"] = hashed_pass
    user_object["role"] = request.role
    user_id = user_data.insert_one(user_object)

    if user_id:
        return {"message": "User created successfully"}
    else:
        return {"message": "Failed to create user"}


@router.post('/login')
def login(request: OAuth2PasswordRequestForm = Depends()):

    user = user_data.find_one({"username": request.username})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'No user found with this {request.username} username')
    if not Hash.verify(user["password"], request.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f'Wrong Username or password')
    
    # Get the user's role
    user_role = user["role"]

    # Create the access token with the user's role
    access_token = create_access_token(data={"sub": user["username"], "role": user_role})
    
    return {"access_token": access_token, "token_type": "bearer"}